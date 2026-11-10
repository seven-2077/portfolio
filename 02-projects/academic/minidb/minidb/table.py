"""表门面（Table）—— 把「堆 + 一堆索引」封装成带约束的表。

职责边界：

* :class:`~minidb.heap.TableHeap` 只管字节怎么进出页，不懂约束；
* :class:`Index` 只管键值对在树里怎么排，不懂该表有哪些列；
* :class:`Table` 负责 SQL 语义：NOT NULL 检查、主键/唯一冲突检查、
  以及**索引维护** —— 每一次 INSERT/UPDATE/DELETE 都要同步所有索引。

索引维护为什么必须在这里而不是执行器里？
因为「行变了索引就得变」是存储层不变式，任何绕过执行器的路径
（未来加的批量导入、REPL 元命令）都不能把它打破。

复合键编码规则（与 btree.py 的唯一性论证呼应）::

    主键索引   key = enc(pk)
    二级索引   key = enc(col1) + enc(col2) + ... + enc(pk)   （无主键则用 enc(rowid) 兜底）
"""

from __future__ import annotations

import struct
from typing import Iterator, Optional

from .btree import BPlusTree
from .catalog import Catalog, IndexInfo, TableInfo
from .codec import decode_rowid, encode_key, encode_rowid
from .errors import DuplicateKeyError, NotNullError, SchemaError, TypeMismatchError
from .heap import TableHeap
from .pager import Pager


class Index:
    """一个索引 = IndexInfo + B+ 树 + 键编码策略。"""

    def __init__(self, pager: Pager, info: IndexInfo, table: TableInfo, catalog: Catalog) -> None:
        self.info = info
        self.table = table
        self._catalog = catalog

        def on_root(root: int) -> None:
            info.root_page = root  # 根分裂了，把新根记进 catalog，提交时一起落盘
            catalog.touch()

        self.tree = BPlusTree(pager, info.root_page, on_root)
        # 索引列 / 主键列的位置（存表 schema 的下标）
        self.positions = [table.column_index(c) for c in info.columns]
        self.pk_positions = [table.column_index(c.name) for c in table.pk_columns]

    # -- 键编码 -------------------------------------------------------------

    def key_for(self, values: tuple, rowid: int) -> bytes:
        """按行值算出该索引下的完整键。"""
        parts = [
            encode_key(values[p], self.table.columns[p].col_type) for p in self.positions
        ]
        # 主键追加只为「索引里没有主键列」的二级索引兜底唯一性：
        # 主键索引自己的 positions 已含主键，再拼一遍会变成 enc(pk)+enc(pk)，
        # 与 planner 传来的单段边界键 enc(pk) 对不上（range 边界全部失准）。
        if self.pk_positions and self.pk_positions[0] not in self.positions:
            pk = self.pk_positions[0]
            parts.append(encode_key(values[pk], self.table.columns[pk].col_type))
        elif not self.pk_positions:
            # 无主键表：拿 rowid 兜底，保证复合键依然全树唯一
            parts.append(struct.pack(">Q", rowid))
        return b"".join(parts)

    def prefix_for(self, values: dict[str, object]) -> Optional[bytes]:
        """按「最左若干列等值」拼前缀；一列都配不上返回 None。"""
        parts: list[bytes] = []
        for name, col_pos in zip(self.info.columns, self.positions):
            low = name.lower()
            if low not in values:
                break
            parts.append(encode_key(values[low], self.table.columns[col_pos].col_type))
        return b"".join(parts) if parts else None

    # -- 查找 ---------------------------------------------------------------

    def find_rowids(self, key: bytes) -> list[int]:
        return [decode_rowid(v) for v in self.tree.search(key)]

    def range_rowids(self, start=None, end=None, start_inclusive=True, end_inclusive=True) -> Iterator[int]:
        for _k, v in self.tree.range_scan(start, end, start_inclusive, end_inclusive):
            yield decode_rowid(v)

    def prefix_rowids(self, prefix: bytes) -> Iterator[int]:
        for _k, v in self.tree.prefix_scan(prefix):
            yield decode_rowid(v)

    def key_exists(self, prefix: bytes, exclude_rowid: Optional[int] = None) -> bool:
        """前缀区间内是否已有条目（UNIQUE 检查用；NULL 值按 SQL 语义豁免）。"""
        for rowid in self.prefix_rowids(prefix):
            if exclude_rowid is None or rowid != exclude_rowid:
                return True
        return False

    # -- 维护 ---------------------------------------------------------------

    def insert_entry(self, values: tuple, rowid: int) -> None:
        self.tree.insert(self.key_for(values, rowid), encode_rowid(rowid))

    def delete_entry(self, values: tuple, rowid: int) -> None:
        self.tree.delete(self.key_for(values, rowid), encode_rowid(rowid))


class Table:
    """一张表：堆 + 索引 + 约束检查。每次语句新建实例（无跨语句缓存）。"""

    def __init__(self, pager: Pager, info: TableInfo, catalog: Catalog) -> None:
        self.info = info
        self.catalog = catalog
        self.heap = TableHeap(pager, info, catalog.touch)
        self.indexes = [Index(pager, idx, info, catalog) for idx in info.indexes]
        # 求值环境：列名(小写) -> 行内下标，表达式解析时查这张表
        self.column_env: dict[str, int] = {c.name.lower(): i for i, c in enumerate(info.columns)}

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.info.columns]

    def _index(self, info: IndexInfo) -> Index:
        for idx in self.indexes:
            if idx.info is info:
                return idx
        raise SchemaError(f"索引不存在: {info.name}")

    # -- 约束检查 -----------------------------------------------------------

    def _check_constraints(self, values: tuple, exclude_rowid: Optional[int] = None) -> None:
        """NOT NULL / 类型（encode_row 内）/ 主键与 UNIQUE 冲突。"""
        for col, v in zip(self.info.columns, values):
            if v is None and (col.not_null or col.primary_key):
                # 主键隐含 NOT NULL（SQL 标准）
                raise NotNullError(f"列 {col.name} 不允许为 NULL")
        for idx_info in self.info.indexes:
            if not idx_info.unique:
                continue
            idx = self._index(idx_info)
            if any(values[p] is None for p in idx.positions):
                continue  # SQL 语义：UNIQUE 列的多个 NULL 互不冲突
            by_col = {n.lower(): values[p] for n, p in zip(idx_info.columns, idx.positions)}
            prefix = idx.prefix_for(by_col)
            if prefix is not None and idx.key_exists(prefix, exclude_rowid):
                cols = ", ".join(idx_info.columns)
                raise DuplicateKeyError(f"唯一约束冲突: {cols} 的值重复")

    # -- 行级 CRUD ----------------------------------------------------------

    def insert(self, values: list) -> int:
        """插入一行，返回 rowid。先做全部只读检查，再动存储。"""
        if len(values) != len(self.info.columns):
            raise SchemaError(f"列数不匹配：表有 {len(self.info.columns)} 列，收到 {len(values)} 列")
        row = tuple(values)
        self._check_constraints(row)
        rowid = self.heap.insert(row)
        for idx in self.indexes:
            idx.insert_entry(row, rowid)
        return rowid

    def get(self, rowid: int) -> Optional[tuple]:
        return self.heap.get(rowid)

    def update(self, rowid: int, old_values: tuple, new_values: tuple) -> int:
        """更新一行，返回新 rowid；同步全部索引。"""
        new_row = tuple(new_values)
        self._check_constraints(new_row, exclude_rowid=rowid)
        new_rowid = self.heap.update(rowid, new_row)
        if new_row != tuple(old_values) or new_rowid != rowid:
            # 行值或位置任一变化，索引条目都要重建
            for idx in self.indexes:
                idx.delete_entry(old_values, rowid)
                idx.insert_entry(new_row, new_rowid)
        return new_rowid

    def delete(self, rowid: int, values: tuple) -> None:
        """删除一行并摘掉全部索引条目。"""
        for idx in self.indexes:
            idx.delete_entry(values, rowid)
        self.heap.delete(rowid)

    def scan(self) -> Iterator[tuple[int, tuple]]:
        """全表顺序扫描（SeqScan 的数据源）。"""
        return self.heap.scan()

    def index_scan(self, idx: Index, **kwargs) -> Iterator[tuple[int, tuple]]:
        """按索引区间取行；索引里有而堆里没有的条目会被跳过（防御性）。"""
        for rowid in idx.range_rowids(**kwargs):
            row = self.heap.get(rowid)
            if row is not None:
                yield rowid, row

    def prefix_scan(self, idx: Index, prefix: bytes) -> Iterator[tuple[int, tuple]]:
        for rowid in idx.prefix_rowids(prefix):
            row = self.heap.get(rowid)
            if row is not None:
                yield rowid, row


def resolve_columns(info: TableInfo, names: list[str]) -> list[int]:
    """把列名列表解析成下标列表（大小写不敏感），重名报错。"""
    out: list[int] = []
    seen: set[int] = set()
    for name in names:
        pos = info.column_index(name)
        if pos in seen:
            raise SchemaError(f"列重复: {name}")
        seen.add(pos)
        out.append(pos)
    return out


__all__ = ["Table", "Index", "resolve_columns"]
