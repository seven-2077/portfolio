"""页式存储管理器（Pager）—— 数据库文件的唯一读写入口。

对标操作系统的**页式存储管理**：

* 数据库文件被切成定长 4096 字节的页，所有读写以页为单位寻址
  （页号 -> 文件偏移 = 页号 × PAGE_SIZE），与 OS 的页表换算如出一辙。
* **缓冲池 + 脏页集**：页先读进内存缓冲，修改只标记脏位；
  提交时由上层（Database）决定何时刷盘 —— 这就是 OS 里
  「脏页延迟写回」的数据库版本。
* **空闲链表**：释放的页把「下一个空闲页号」写在自己的前 8 字节，
  形成单链；分配时优先弹链头复用，避免文件只增不减。
  这与 OS 物理页帧的 free list 是同一个数据结构。

文件头页（page 0）保存全局元信息：magic、版本、页大小、
下一个可用页号、空闲链表头、catalog 起始页。
这四样东西必须与脏页**同一次提交**落盘，否则崩溃后会不一致 ——
所以它们的变化也表现为「page 0 变脏」，走同一条 WAL 路径。
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

from .errors import StorageError

PAGE_SIZE = 4096

# 各类页的类型字节（页的第一个字节）
PAGE_HEAP = 1        # 堆数据页（表的行存储）
PAGE_BTREE_LEAF = 2  # B+ 树叶子
PAGE_BTREE_INTERNAL = 3  # B+ 树内部
PAGE_CATALOG = 5     # 系统表（catalog）数据页
# 4 保留；空闲页不带类型（内容是空闲链表指针）

MAGIC = b"MINIDB01"
FORMAT_VERSION = 1

# page 0 布局：magic(8) version(4) page_size(4) next_page(8) freelist_head(8) catalog_start(8)
_HEADER = struct.Struct(">8sIIQQQ")
HEADER_SIZE = _HEADER.size  # 40


class Pager:
    """管理一个数据库文件：页缓存、分配/释放、批量刷盘。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        created = not self.path.exists()
        # buffering=0 => 原始无缓冲 FileIO：每次 write 都直接进入 OS。
        # 这对崩溃模拟很关键 —— 进程被 kill 后 OS 页缓存仍在，
        # 与真实进程崩溃的语义一致（丢的只是用户态缓冲）。
        self._file = open(self.path, "w+b" if created else "r+b", buffering=0)
        self._buffers: dict[int, bytearray] = {}
        self._dirty: set[int] = set()
        # 头页三字段走属性 setter：任何变化都把 page 0 标脏，
        # 它们才能随脏页集一起进 WAL —— 否则崩溃恢复后
        # 「空闲链表头 / 下一页号 / catalog 起始页」会与实际页状态脱节。
        self._next_page_no = 0
        self._freelist_head = 0
        self._catalog_start = 0
        if created:
            self._next_page_no = 1  # page 0 自己占位
            self._write_header()
            self._sync_page0()      # 新库立即落盘，避免「文件存在但内容是空的」
        else:
            self._read_header()

    # 头页字段（setter 自动重打包并标脏 page 0，见类文档）----------------------

    def _touch_header(self) -> None:
        """头页字段变了：把最新值重新打包进 page 0 并标脏。

        只标脏**不重打包**是不够的 —— 脏页快照取的是缓冲区里的字节，
        不重新 pack 就会把「旧头」当「新头」写进 WAL/数据文件，
        崩溃恢复后 catalog 起始页、空闲链表头全部对不上（联调时踩过）。
        """
        buf = self._buffers.get(0)
        if buf is None:                     # 防御：正常路径下 init 已装好
            self._write_header()
            return
        _HEADER.pack_into(
            buf, 0, MAGIC, FORMAT_VERSION, PAGE_SIZE,
            self._next_page_no, self._freelist_head, self._catalog_start,
        )
        self._dirty.add(0)

    @property
    def next_page_no(self) -> int:
        return self._next_page_no

    @next_page_no.setter
    def next_page_no(self, value: int) -> None:
        self._next_page_no = value
        self._touch_header()

    @property
    def freelist_head(self) -> int:
        return self._freelist_head

    @freelist_head.setter
    def freelist_head(self, value: int) -> None:
        self._freelist_head = value
        self._touch_header()

    @property
    def catalog_start(self) -> int:
        return self._catalog_start

    @catalog_start.setter
    def catalog_start(self, value: int) -> None:
        self._catalog_start = value
        self._touch_header()

    # -- 头页 ---------------------------------------------------------------

    def _write_header(self) -> None:
        buf = bytearray(PAGE_SIZE)
        _HEADER.pack_into(
            buf, 0, MAGIC, FORMAT_VERSION, PAGE_SIZE,
            self.next_page_no, self.freelist_head, self.catalog_start,
        )
        self._buffers[0] = buf
        self._dirty.add(0)

    def _read_header(self) -> None:
        buf = self._read_from_disk(0)
        magic, version, page_size, next_page, free_head, cat_start = _HEADER.unpack_from(buf, 0)
        if magic != MAGIC:
            raise StorageError(f"不是有效的 MiniDB 数据库文件（magic 不匹配）: {self.path}")
        if version != FORMAT_VERSION or page_size != PAGE_SIZE:
            raise StorageError(f"不支持的数据库格式: version={version} page_size={page_size}")
        # 直接写 backing 字段：打开数据库不是修改，不该把 page 0 标脏
        self._next_page_no = next_page
        self._freelist_head = free_head
        self._catalog_start = cat_start
        self._buffers[0] = buf

    def reload_header(self) -> None:
        """从磁盘重读头页（语句失败回滚后，把分配指针拨回磁盘真相）。"""
        self._read_header()

    def _sync_page0(self) -> None:
        self.write_images({0: bytes(self._buffers[0])})
        self._dirty.discard(0)

    # -- 页读写 -------------------------------------------------------------

    def _read_from_disk(self, page_no: int) -> bytearray:
        buf = bytearray(PAGE_SIZE)
        self._file.seek(page_no * PAGE_SIZE)
        chunk = self._file.read(PAGE_SIZE)  # 文件尾部/不足一页时读到多少算多少
        buf[: len(chunk)] = chunk           # 其余补零：未写过的页视为空页
        return buf

    def read(self, page_no: int) -> bytearray:
        """读一页（进缓冲）。返回的是共享缓冲，**只读用途**；要修改请用 buffer()。"""
        if page_no not in self._buffers:
            self._buffers[page_no] = self._read_from_disk(page_no)
        return self._buffers[page_no]

    def buffer(self, page_no: int) -> bytearray:
        """读一页并**立即标脏**，供调用方就地修改。"""
        buf = self.read(page_no)
        self._dirty.add(page_no)
        return buf

    def mark_dirty(self, page_no: int) -> None:
        self._dirty.add(page_no)

    # -- 分配 / 释放 --------------------------------------------------------

    def allocate(self) -> int:
        """分配一页：优先复用空闲链表，否则向文件尾部要新页。

        复用页会先整体清零 —— 防止上一任使用者的数据（可能包含别的表的
        行内容）泄漏给新主人，这也是安全编码的常规要求。
        """
        if self.freelist_head:
            page = self.freelist_head
            buf = self.read(page)
            nxt = int.from_bytes(buf[:8], "big")
            self.freelist_head = nxt  # 属性 setter 会把 page 0 标脏
            buf[:] = bytes(PAGE_SIZE)
            self._dirty.add(page)
            return page
        page = self.next_page_no
        self.next_page_no += 1  # 同样会标脏 page 0
        return page

    def free(self, page_no: int) -> None:
        """把页挂回空闲链表头（LIFO，复用局部性最好）。"""
        if page_no == 0:
            raise StorageError("不能释放头页")
        buf = self.buffer(page_no)
        buf[:] = bytes(PAGE_SIZE)
        buf[:8] = self.freelist_head.to_bytes(8, "big")
        self.freelist_head = page_no

    # -- 提交辅助 -----------------------------------------------------------

    def dirty_images(self) -> dict[int, bytes]:
        """取当前全部脏页的快照（页号升序，便于调试观察）。"""
        return {p: bytes(self._buffers[p]) for p in sorted(self._dirty)}

    def write_images(self, images: dict[int, bytes]) -> None:
        """把页映像写进数据库文件并 fsync（提交协议的第 3 步）。"""
        for page_no, data in images.items():
            self._file.seek(page_no * PAGE_SIZE)
            self._file.write(data)
        os.fsync(self._file.fileno())

    def clear_dirty(self) -> None:
        self._dirty.clear()

    def discard_buffers(self) -> None:
        """丢弃全部内存缓冲与脏位 —— 语句失败/开始时回到磁盘上的真相。"""
        self._buffers.clear()
        self._dirty.clear()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    @property
    def closed(self) -> bool:
        return self._file.closed
