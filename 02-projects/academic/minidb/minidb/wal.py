"""预写日志（WAL）与崩溃恢复。

提交协议（一条语句 = 一个隐式事务，四步）::

    ① 把全部脏页的「页映像」追加进 .wal 文件（PAGE 记录）
    ② 追加一条 COMMIT 记录，然后 fsync(WAL)      ← 事务的持久化点
    ③ 把脏页写回数据库文件，然后 fsync(DB)
    ④ 截断 WAL（checkpoint）

为什么用**整页映像**而不是生理日志（页内记录 + 偏移）？
教学库的恢复只需要 redo，整页映像让恢复退化成「按 LSN 顺序把页抄回去」，
天然幂等（抄两遍结果一样），完全不需要 ARIES 的 undo / CLRs。
代价是日志量大（每页 4KB），这正是教学取舍，README 里有展开。

为什么要有 COMMIT 记录？崩溃可能留下**撕裂的尾记录**（写了一半）。
恢复只认到最后一条 COMMIT 为止的记录，其后的全部丢弃 ——
这保证了「要么整条语句生效，要么完全不生效」的原子性，
与 408 里「日志 + 提交点」的恢复语义一致。

恢复（:func:`recover_database`，在打开数据库时执行）::

    扫描 WAL -> CRC 校验逐条验证（坏记录 = 崩溃撕裂点，停）
             -> 找到最后一条 COMMIT
             -> 把它之前的页映像按序写回 DB 文件 -> fsync -> 截断 WAL

崩溃点分析（对应测试用例）：
* 崩在 ①~② 之间：WAL 无 COMMIT -> 语句丢弃（它本来就没提交成功）
* 崩在 ②~③ 之间：WAL 有 COMMIT，DB 没写 -> redo 补齐
* 崩在 ③~④ 之间：DB 已写，WAL 还在 -> redo 幂等重放，结果不变
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

from .errors import StorageError
from .pager import PAGE_SIZE

# 记录头：type(1) lsn(8) page_no(8) length(4) crc32(4) = 25 字节
# LSN 直接用记录在 WAL 里的字节偏移 —— 与 PostgreSQL 的 LSN 定义一致，
# 「日志顺序号」就是文件位置，排序即时间序。
_HDR = struct.Struct(">BQQII")
_HDR_BODY = struct.Struct(">BQQI")  # 参与 CRC 的前 21 字节

WAL_PAGE = 1
WAL_COMMIT = 2


class Wal:
    """WAL 文件的追加写句柄（无缓冲 FileIO，写入立即进 OS）。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._file = open(self.path, "w+b", buffering=0)

    def _append(self, record: bytes) -> None:
        self._file.seek(0, 2)  # 追加到尾部
        self._file.write(record)

    def append_page(self, page_no: int, image: bytes) -> None:
        if len(image) != PAGE_SIZE:
            raise StorageError("WAL 记录必须是完整页映像")
        lsn = self._file.seek(0, 2)
        crc = zlib.crc32(image, zlib.crc32(_HDR_BODY.pack(WAL_PAGE, lsn, page_no, len(image))))
        self._append(_HDR.pack(WAL_PAGE, lsn, page_no, len(image), crc) + image)

    def append_commit(self) -> None:
        lsn = self._file.seek(0, 2)
        crc = zlib.crc32(_HDR_BODY.pack(WAL_COMMIT, lsn, 0, 0))
        self._append(_HDR.pack(WAL_COMMIT, lsn, 0, 0, crc))

    def sync(self) -> None:
        """fsync —— 提交协议的第 ② 步，跨过这里事务才算数。"""
        os.fsync(self._file.fileno())

    def reset(self) -> None:
        """截断日志（checkpoint 后 WAL 归零，LSN 也从头计）。"""
        self._file.truncate(0)
        self._file.seek(0)

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    @property
    def closed(self) -> bool:
        return self._file.closed


def recover_database(db_path: Path, wal_path: Path) -> int:
    """打开前的崩溃恢复：重放最后一次 COMMIT 之前的页映像（纯 redo）。

    返回重放的页数（0 表示无需恢复）。恢复完成后 WAL 被截断。
    """
    if not wal_path.exists():
        return 0
    if not db_path.exists():
        # 数据库文件都还没有，日志必然孤立（比如首次建库前崩溃），直接丢弃
        wal_path.write_bytes(b"")
        return 0

    data = wal_path.read_bytes()
    pos = 0
    entries: list[tuple[int, int, bytes]] = []  # (位置, 页号, 映像)
    last_commit = -1
    while pos + _HDR.size <= len(data):
        rtype, _lsn, page_no, length, crc = _HDR.unpack_from(data, pos)
        end = pos + _HDR.size + length
        if end > len(data):
            break  # 尾部记录没写完（撕裂）
        payload = data[pos + _HDR.size : end]
        if zlib.crc32(payload, zlib.crc32(data[pos : pos + _HDR_BODY.size])) != crc:
            break  # CRC 不过：崩溃撕裂点，之前的是完整的
        if rtype == WAL_PAGE:
            entries.append((pos, page_no, payload))
        elif rtype == WAL_COMMIT:
            last_commit = pos  # 只认最后一条提交点
        else:
            break  # 未知类型，保守停止
        pos = end

    committed = [(pg, img) for (pos, pg, img) in entries if pos < last_commit]
    if not committed:
        wal_path.write_bytes(b"")
        return 0

    with open(db_path, "r+b", buffering=0) as f:
        for image_page_no, image in committed:
            f.seek(image_page_no * PAGE_SIZE)
            f.write(image)
        os.fsync(f.fileno())
    wal_path.write_bytes(b"")  # 恢复完成，日志使命结束
    return len(committed)
