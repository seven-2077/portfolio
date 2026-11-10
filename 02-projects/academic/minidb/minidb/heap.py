"""堆存储：槽式页（slotted page）+ 表级行堆。

页布局（对标 PostgreSQL / SQL Server 的经典设计）::

    [页头 14B][槽目录 4B × N ......... 空闲区 ......... 行数据 →]

* 槽目录从前往后长：每槽 ``offset u16 + length u16``，``offset=0xFFFF`` 表示墓碑（已删）。
* 行数据从页尾往前长，新行落在空闲区高端。
* 删除只把槽改成墓碑（O(1)），产生的碎片在需要时 compact 一次性压实。

为什么用槽目录而不是「行后面直接跟长度」？因为 DELETE / UPDATE
不需要搬动其它行，只改 4 字节的目录项；变长行（TEXT）也仍然能原地删除。
这是 408 数据结构课里「间接层」思想的直接应用：多加一层目录，
换来 O(1) 删除与紧凑的空间管理。

表级的 :class:`TableHeap` 把多个堆页用 ``next`` 指针串成链，
顺序扫描顺着链走即可 —— 与链表遍历完全一致。
"""

from __future__ import annotations

import struct
from typing import Iterator

from .codec import decode_row, encode_row
from .errors import StorageError
from .pager import PAGE_HEAP, PAGE_SIZE, Pager

# 页头：type(1) flags(1) next(8) slot_count(2) free_upper(2) = 14 字节
_HDR = struct.Struct(">BBQHH")
_HDR_SIZE = _HDR.size  # 14
_SLOT = struct.Struct(">HH")
_TOMBSTONE = 0xFFFF


class HeapPage:
    """单个槽式堆页的视图（就地修改 Pager 缓冲）。"""

    __slots__ = ("data",)

    def __init__(self, data: bytearray) -> None:
        self.data = data

    # -- 构造 / 校验 --------------------------------------------------------

    @classmethod
    def init_new(cls, data: bytearray, next_page: int = 0) -> "HeapPage":
        """把一页初始化成空堆页。"""
        data[:] = bytes(PAGE_SIZE)
        _HDR.pack_into(data, 0, PAGE_HEAP, 0, next_page, 0, PAGE_SIZE)
        return cls(data)

    @classmethod
    def wrap(cls, data: bytearray) -> "HeapPage":
        if data[0] != PAGE_HEAP:
            raise StorageError(f"页类型错误：期望堆页(1)，实际为 {data[0]}")
        return cls(data)

    # -- 页头字段 -----------------------------------------------------------

    @property
    def next_page(self) -> int:
        return _HDR.unpack_from(self.data, 0)[2]

    @next_page.setter
    def next_page(self, value: int) -> None:
        self.data[2:10] = struct.pack(">Q", value)

    @property
    def slot_count(self) -> int:
        return _HDR.unpack_from(self.data, 0)[3]

    def _free_upper(self) -> int:
        return _HDR.unpack_from(self.data, 0)[4]

    def _set_free_upper(self, v: int) -> None:
        self.data[12:14] = struct.pack(">H", v)

    def _free_lower(self) -> int:
        # 槽目录紧跟页头，长度由槽数决定，无需存储
        return _HDR_SIZE + self.slot_count * 4

    def _slot_off(self, slot: int) -> int:
        return _HDR_SIZE + slot * 4

    def _get_slot(self, slot: int) -> tuple[int, int]:
        return _SLOT.unpack_from(self.data, self._slot_off(slot))

    def _set_slot(self, slot: int, offset: int, length: int) -> None:
        _SLOT.pack_into(self.data, self._slot_off(slot), offset, length)

    def _set_slot_count(self, n: int) -> None:
        self.data[10:12] = struct.pack(">H", n)

    # -- 基本操作 -----------------------------------------------------------

    def get(self, slot: int) -> bytes | None:
        """取槽位上的记录；墓碑或越界返回 None。"""
        if slot >= self.slot_count:
            return None
        offset, length = self._get_slot(slot)
        if offset == _TOMBSTONE:
            return None
        return bytes(self.data[offset : offset + length])

    def free_space(self) -> int:
        return self._free_upper() - self._free_lower()

    def _find_tombstone(self) -> int | None:
        for slot in range(self.slot_count):
            if self._get_slot(slot)[0] == _TOMBSTONE:
                return slot
        return None

    def has_tombstone(self) -> bool:
        return self._find_tombstone() is not None

    def insert(self, record: bytes) -> int | None:
        """插入一条记录，返回槽号；空间不足（含压实后仍不足）返回 None。"""
        size = len(record)
        if size + 4 > PAGE_SIZE - _HDR_SIZE:
            raise StorageError("行记录超过单页容量")
        tomb = self._find_tombstone()
        need = size + (0 if tomb is not None else 4)  # 复用墓碑槽不占新目录项
        if self.free_space() < need:
            self.compact()
            if self.free_space() < need:
                return None
        upper = self._free_upper() - size
        self.data[upper : upper + size] = record
        self._set_free_upper(upper)
        if tomb is not None:
            slot = tomb
        else:
            slot = self.slot_count
            self._set_slot_count(slot + 1)
        self._set_slot(slot, upper, size)
        return slot

    def delete(self, slot: int) -> bool:
        """打墓碑。真正回收空间要等下一次 compact。"""
        if slot >= self.slot_count:
            return False
        offset, _ = self._get_slot(slot)
        if offset == _TOMBSTONE:
            return False
        self._set_slot(slot, _TOMBSTONE, 0)
        return True

    def update(self, slot: int, record: bytes) -> int | None:
        """原地更新一条记录，返回新槽号（可能因搬迁而变）；放不下返回 None。

        关键顺序：**先评估可行性再动手** —— 如果先打墓碑再发现放不下，
        原记录就丢了。所以这里只有「原地覆盖」或「确认放得下才重建」两条路。
        """
        if slot >= self.slot_count:
            return None
        offset, length = self._get_slot(slot)
        if offset == _TOMBSTONE:
            return None
        if len(record) <= length:
            self.data[offset : offset + len(record)] = record
            self._set_slot(slot, offset, len(record))
            return slot
        # 放不下：腾出旧空间 + 压实后是否足够？
        if self.free_space() + length < len(record):
            return None
        self.delete(slot)
        self.compact()
        new_slot = self.insert(record)
        return new_slot  # insert 会优先复用刚腾出的墓碑槽

    def compact(self) -> None:
        """把所有存活记录紧凑搬到页尾，合并碎片。"""
        pos = PAGE_SIZE
        for slot in range(self.slot_count):
            offset, length = self._get_slot(slot)
            if offset == _TOMBSTONE:
                continue
            pos -= length
            # 右侧切片先求值再赋值，重叠也安全
            self.data[pos : pos + length] = self.data[offset : offset + length]
            self._set_slot(slot, pos, length)
        self._set_free_upper(pos)

    def iter_records(self) -> Iterator[tuple[int, bytes]]:
        for slot in range(self.slot_count):
            record = self.get(slot)
            if record is not None:
                yield slot, record


class TableHeap:
    """一张表的行堆：页链 + 行编解码 + 行级 CRUD。"""

    def __init__(self, pager: Pager, info, touch) -> None:
        self.pager = pager
        self.info = info        # catalog.TableInfo（持有 first/last page 与列定义）
        self._touch = touch     # 结构变化时通知 catalog 标脏

    # -- 页链 ---------------------------------------------------------------

    def _append_page(self) -> int:
        page = self.pager.allocate()
        HeapPage.init_new(self.pager.buffer(page))
        if self.info.last_page:
            last = HeapPage.wrap(self.pager.buffer(self.info.last_page))
            last.next_page = page
        else:
            self.info.first_page = page
        self.info.last_page = page
        self._touch()
        return page

    def _fits(self, page_no: int, size: int) -> bool:
        """这一页装得下 size 字节的记录吗？必要时先压实再判断。

        压实前先算一个**乐观上界**（目录以外全空），
        上界都不够就不必弄脏这一页了 —— 避免无谓的写放大。
        """
        heap = HeapPage.wrap(self.pager.read(page_no))
        need = size + (0 if heap.has_tombstone() else 4)
        if heap.free_space() >= need:
            return True
        if PAGE_SIZE - _HDR_SIZE - heap.slot_count * 4 >= need:
            heap = HeapPage.wrap(self.pager.buffer(page_no))
            heap.compact()
            return heap.free_space() >= need
        return False

    def _find_page(self, size: int) -> int | None:
        # 先试末页：插入以追加为主，末页命中率最高
        last = self.info.last_page
        if last and self._fits(last, size):
            return last
        page = self.info.first_page
        while page:
            if page != last and self._fits(page, size):
                return page
            page = HeapPage.wrap(self.pager.read(page)).next_page
        return None

    # -- 行级操作 -----------------------------------------------------------

    def insert(self, values) -> int:
        """插入一行（已校验过的值），返回 rowid。"""
        record = encode_row(values, self.info.columns)
        page = self._find_page(len(record))
        if page is None:
            page = self._append_page()
        heap = HeapPage.wrap(self.pager.buffer(page))
        slot = heap.insert(record)
        if slot is None:  # 末页在压实后仍装不下（极端碎片）→ 兜底新开一页
            page = self._append_page()
            heap = HeapPage.wrap(self.pager.buffer(page))
            slot = heap.insert(record)
            if slot is None:
                raise StorageError("行记录超过单页容量")
        return (page << 16) | slot

    def get(self, rowid: int):
        """按 rowid 取行，返回值元组；行不存在返回 None。"""
        page, slot = rowid >> 16, rowid & 0xFFFF
        if page >= self.pager.next_page_no:
            raise StorageError(f"无效的行引用: rowid={rowid}")
        heap = HeapPage.wrap(self.pager.read(page))
        record = heap.get(slot)
        if record is None:
            return None
        return decode_row(record, self.info.columns)

    def update(self, rowid: int, values) -> int:
        """用新值替换一行，返回**新** rowid（可能搬迁到别的页）。"""
        record = encode_row(values, self.info.columns)
        page, slot = rowid >> 16, rowid & 0xFFFF
        heap = HeapPage.wrap(self.pager.buffer(page))
        new_slot = heap.update(slot, record)
        if new_slot is not None:
            return (page << 16) | new_slot
        # 本页放不下：先在别处落地，再摘掉旧行（顺序保证中途失败也不丢数据）
        target = self._find_page(len(record))
        if target is None:
            target = self._append_page()
        other = HeapPage.wrap(self.pager.buffer(target))
        new_slot = other.insert(record)
        if new_slot is None:
            target = self._append_page()
            other = HeapPage.wrap(self.pager.buffer(target))
            new_slot = other.insert(record)
            if new_slot is None:
                raise StorageError("行记录超过单页容量")
        old = HeapPage.wrap(self.pager.buffer(page))
        old.delete(slot)
        return (target << 16) | new_slot

    def delete(self, rowid: int) -> None:
        page, slot = rowid >> 16, rowid & 0xFFFF
        heap = HeapPage.wrap(self.pager.buffer(page))
        heap.delete(slot)

    def scan(self) -> Iterator[tuple[int, tuple]]:
        """顺序扫描全表，产出 (rowid, 行值)。"""
        page = self.info.first_page
        while page:
            heap = HeapPage.wrap(self.pager.read(page))
            for slot, record in heap.iter_records():
                yield (page << 16) | slot, decode_row(record, self.info.columns)
            page = heap.next_page
