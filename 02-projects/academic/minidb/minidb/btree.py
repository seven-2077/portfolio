"""B+ 树索引：插入、等值查找、范围扫描、节点分裂、叶子链表。

设计取舍（「为什么」是本模块的灵魂）：

* **键必须在树内严格唯一**。主键索引天然唯一；二级索引若只存列值，
  重复值在叶子分裂时可能被分隔符劈到两侧，等值查找就会漏掉左边那份。
  解法：二级索引键 = ``enc(列值) + enc(主键)`` 复合编码（无主键表用 rowid 兜底）。
  由于 encode_key 是**前缀自由**的（TEXT 带终结符、INT/FLOAT 定长），
  拼接后的字节序仍然 == 元组序，树内比较依旧是 memcmp。
  InnoDB 二级索引末尾拼主键、SQLite 的 (key, rowid) 用的正是同一招。

* **叶子链表**：叶子节点持有 next 指针串成有序链。范围扫描定位到起点后
  顺链走即可，不必每次比较都回树下降 —— 这是 B+ 树区别于 B 树的核心，
  也是 408 数据结构大题的高频考点。

* **分裂即上浮**：叶分裂把右半首键作为分隔符**复制**上去（右叶仍留着它）；
  内部分裂把中位键**搬走**上浮（内部节点不留）。递归返回
  ``(上浮键, 右兄弟页号)``，父节点插一条即可，天然支持多层。

* **节点整体重写**：节点内容是紧凑数组序列化，不做槽目录。
  因为 B+ 树节点的操作以「改一条 -> 整体重写」为主（4KB 以内），
  槽目录的 O(1) 删除优势用不上，反而增加复杂度。

* **删除不做再平衡**（刻意取舍）：只从叶子里摘掉条目。
  正确性不受影响 —— 内部分隔符只是路由提示，查找/范围扫描照常工作；
  代价是大量删除后页利用率下降。借位/合并列入 Roadmap，
  教学阶段先把「写对」和「讲清楚」做扎实（SQLite 同样是惰性删除）。
"""

from __future__ import annotations

import bisect
import struct
from typing import Callable, Iterator, Optional

from .errors import StorageError
from .pager import PAGE_BTREE_INTERNAL, PAGE_BTREE_LEAF, PAGE_SIZE, Pager

# 叶页头：type(1) flags(1) next(8) count(2) = 12 字节
_LEAF_HDR = struct.Struct(">BBQH")
# 内部页头：type(1) flags(1) count(2) = 4 字节
_INT_HDR = struct.Struct(">BBH")
# 叶条目：klen(2) vlen(2) + key + value
_KV = struct.Struct(">HH")
# 内部条目里的子页号 / 末子指针
_CHILD = struct.Struct(">Q")


def _ser_leaf(next_page: int, entries: list[tuple[bytes, bytes]]) -> bytes:
    out = bytearray(_LEAF_HDR.pack(PAGE_BTREE_LEAF, 0, next_page, len(entries)))
    for key, value in entries:
        out += _KV.pack(len(key), len(value)) + key + value
    return bytes(out)


def _de_leaf(data: bytes) -> tuple[int, list[tuple[bytes, bytes]]]:
    _t, _f, next_page, count = _LEAF_HDR.unpack_from(data, 0)
    off = _LEAF_HDR.size
    entries: list[tuple[bytes, bytes]] = []
    for _ in range(count):
        klen, vlen = _KV.unpack_from(data, off)
        off += _KV.size
        if off + klen + vlen > len(data):
            raise StorageError("B+ 树叶节点损坏：条目越界")
        entries.append((bytes(data[off : off + klen]), bytes(data[off + klen : off + klen + vlen])))
        off += klen + vlen
    return next_page, entries


def _ser_internal(keys: list[bytes], children: list[int]) -> bytes:
    out = bytearray(_INT_HDR.pack(PAGE_BTREE_INTERNAL, 0, len(keys)))
    for i, key in enumerate(keys):
        out += _CHILD.pack(children[i]) + struct.pack(">H", len(key)) + key
    out += _CHILD.pack(children[-1])
    return bytes(out)


def _de_internal(data: bytes) -> tuple[list[bytes], list[int]]:
    _t, _f, count = _INT_HDR.unpack_from(data, 0)
    off = _INT_HDR.size
    keys: list[bytes] = []
    children: list[int] = []
    for _ in range(count):
        (child,) = _CHILD.unpack_from(data, off)
        off += _CHILD.size
        (klen,) = struct.unpack_from(">H", data, off)
        off += 2
        if off + klen > len(data):
            raise StorageError("B+ 树内部节点损坏：条目越界")
        keys.append(bytes(data[off : off + klen]))
        off += klen
        children.append(child)
    (last,) = _CHILD.unpack_from(data, off)
    children.append(last)
    return keys, children


class BPlusTree:
    """一棵（单文件内的）B+ 树。root 页号变化时回调 on_root_change。"""

    def __init__(
        self,
        pager: Pager,
        root_page: int,
        on_root_change: Optional[Callable[[int], None]] = None,
    ) -> None:
        self.pager = pager
        self.root_page = root_page
        self.on_root_change = on_root_change

    @classmethod
    def create(cls, pager: Pager, on_root_change=None) -> "BPlusTree":
        """建一棵空树：分配一个空叶作为根。"""
        page = pager.allocate()
        # 必须补零到整页：bytearray 的切片赋值会**改变长度**，
        # 直接 `[:] = payload` 会把 4096 字节的页截成十几字节，
        # 后续 WAL 校验（要求完整页映像）就会当场报错。
        payload = _ser_leaf(0, [])
        pager.buffer(page)[:] = payload + bytes(PAGE_SIZE - len(payload))
        return cls(pager, page, on_root_change)

    # -- 节点读写 -----------------------------------------------------------

    def _load(self, page_no: int) -> tuple[int, object]:
        data = self.pager.read(page_no)
        ptype = data[0]
        if ptype == PAGE_BTREE_LEAF:
            next_page, entries = _de_leaf(bytes(data))
            return ptype, (next_page, entries)
        if ptype == PAGE_BTREE_INTERNAL:
            keys, children = _de_internal(bytes(data))
            return ptype, (keys, children)
        raise StorageError(f"页 {page_no} 不是 B+ 树节点（type={ptype}），可能已损坏")

    def _store(self, page_no: int, payload: bytes) -> None:
        if len(payload) > PAGE_SIZE:
            raise StorageError("B+ 树节点序列化后超出页大小")
        # 用零填充到整页，避免上一次的残留字节留在页尾
        self.pager.buffer(page_no)[:] = payload + bytes(PAGE_SIZE - len(payload))

    # -- 查找路径 -----------------------------------------------------------

    def _descend(self, key: bytes) -> int:
        """从根下降到 key 应在的叶页。

        ``bisect_right`` 给出「第一个严格大于 key 的分隔符」下标，
        即 key 落在 ``[keys[i-1], keys[i])`` 区间 —— 与插入时的
        分隔符语义（左 < sep <= 右）严格互逆，查找才不会走偏。
        """
        page = self.root_page
        while True:
            ptype, payload = self._load(page)
            if ptype == PAGE_BTREE_LEAF:
                return page
            keys, children = payload
            page = children[bisect.bisect_right(keys, key)]

    def _leftmost_leaf(self) -> int:
        page = self.root_page
        while True:
            ptype, payload = self._load(page)
            if ptype == PAGE_BTREE_LEAF:
                return page
            _keys, children = payload
            page = children[0]

    # -- 公开 API -----------------------------------------------------------

    def insert(self, key: bytes, value: bytes) -> None:
        if len(key) + len(value) + _KV.size + _LEAF_HDR.size > PAGE_SIZE:
            raise StorageError("索引键过长，放不进一个 B+ 树节点")
        split = self._insert(self.root_page, key, value)
        if split is not None:
            sep, right = split
            # 根分裂：长出一层，这是 B+ 树高度唯一的增长方式
            new_root = self.pager.allocate()
            self._store(new_root, _ser_internal([sep], [self.root_page, right]))
            self.root_page = new_root
            if self.on_root_change:
                self.on_root_change(new_root)

    def _insert(self, page_no: int, key: bytes, value: bytes) -> Optional[tuple[bytes, int]]:
        ptype, payload = self._load(page_no)
        if ptype == PAGE_BTREE_LEAF:
            _next, entries = payload
            entries.insert(bisect.bisect_left([k for k, _ in entries], key), (key, value))
            serialized = _ser_leaf(_next, entries)
            if len(serialized) > PAGE_SIZE:
                return self._split_leaf(page_no, _next, entries)
            self._store(page_no, serialized)
            return None
        keys, children = payload
        idx = bisect.bisect_right(keys, key)
        split = self._insert(children[idx], key, value)
        if split is None:
            return None
        sep, right = split
        keys.insert(idx, sep)
        children.insert(idx + 1, right)
        serialized = _ser_internal(keys, children)
        if len(serialized) > PAGE_SIZE:
            return self._split_internal(page_no, keys, children)
        self._store(page_no, serialized)
        return None

    def _split_leaf(self, page_no: int, next_page: int, entries) -> tuple[bytes, int]:
        mid = len(entries) // 2
        if mid == 0 or mid == len(entries):
            raise StorageError("B+ 树叶节点分裂失败：条目数不足")
        left, right = entries[:mid], entries[mid:]
        right_page = self.pager.allocate()
        # 分隔符 = 右半首键（右叶仍保留副本）；左叶 next 指向新右叶
        self._store(page_no, _ser_leaf(right_page, left))
        self._store(right_page, _ser_leaf(next_page, right))
        return right[0][0], right_page

    def _split_internal(self, page_no: int, keys: list[bytes], children: list[int]) -> tuple[bytes, int]:
        mid = len(keys) // 2
        promoted = keys[mid]
        left_keys, left_children = keys[:mid], children[: mid + 1]
        right_keys, right_children = keys[mid + 1 :], children[mid + 1 :]
        right_page = self.pager.allocate()
        # 内部分裂是「搬走」中位键：它上浮到父节点，自己不留
        self._store(page_no, _ser_internal(left_keys, left_children))
        self._store(right_page, _ser_internal(right_keys, right_children))
        return promoted, right_page

    def search(self, key: bytes) -> list[bytes]:
        """等值查找，返回全部命中值（键唯一时至多一个）。"""
        page = self._descend(key)
        ptype, payload = self._load(page)
        _next, entries = payload
        pos = bisect.bisect_left([k for k, _ in entries], key)
        if pos < len(entries) and entries[pos][0] == key:
            return [entries[pos][1]]
        return []

    def range_scan(
        self,
        start: bytes | None = None,
        end: bytes | None = None,
        start_inclusive: bool = True,
        end_inclusive: bool = True,
    ) -> Iterator[tuple[bytes, bytes]]:
        """范围扫描：定位起点后沿叶子链顺序产出。"""
        if start is None:
            page = self._leftmost_leaf()
            pos = 0
        else:
            page = self._descend(start)
            _t, payload = self._load(page)
            _next, entries = payload
            keys = [k for k, _ in entries]
            pos = bisect.bisect_left(keys, start) if start_inclusive else bisect.bisect_right(keys, start)
        while page:
            ptype, payload = self._load(page)
            if ptype != PAGE_BTREE_LEAF:
                raise StorageError("B+ 树叶子链断裂")
            next_page, entries = payload
            for i in range(pos, len(entries)):
                key, value = entries[i]
                if end is not None:
                    # 上界判停：key 已越过 end（或撞上 end 但要求开区间）
                    # 就该收手。注意必须是 key > end —— 写成 key < end 会
                    # 在第一个元素就退出，范围扫描直接返回空（联调时踩过）。
                    if key > end or (key == end and not end_inclusive):
                        return
                yield key, value
            page, pos = next_page, 0

    def prefix_scan(self, prefix: bytes) -> Iterator[tuple[bytes, bytes]]:
        """前缀扫描：用于复合键的「最左列等值」定位（二级索引）。"""
        page = self._descend(prefix)
        _t, payload = self._load(page)
        _next, entries = payload
        pos = bisect.bisect_left([k for k, _ in entries], prefix)
        while page:
            ptype, payload = self._load(page)
            if ptype != PAGE_BTREE_LEAF:
                raise StorageError("B+ 树叶子链断裂")
            next_page, entries = payload
            for i in range(pos, len(entries)):
                key, value = entries[i]
                if not key.startswith(prefix):
                    return  # 键有序，前缀区间到此结束
                yield key, value
            page, pos = next_page, 0

    def delete(self, key: bytes, value: bytes) -> bool:
        """删除一条精确的 (键, 值)。不做再平衡（见模块 docstring）。"""
        page = self._descend(key)
        ptype, payload = self._load(page)
        if ptype != PAGE_BTREE_LEAF:
            raise StorageError("B+ 树结构损坏")
        _next, entries = payload
        for i, (k, v) in enumerate(entries):
            if k == key and v == value:
                del entries[i]
                self._store(page, _ser_leaf(_next, entries))
                return True
        return False
