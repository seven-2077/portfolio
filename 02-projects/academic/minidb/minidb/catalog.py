"""系统目录（catalog）—— 数据库的「元数据的元数据」。

保存每张表的列定义、堆页链的首尾页、以及所有索引的根页号。
对标 SQLite：SQLite 把 schema 存成一张普通的 ``sqlite_schema`` 表；
MiniDB 选择把 catalog 序列化成 JSON 存在一条页链上 —— 少实现一个
「系统表自举」问题，代价是不能用 SQL 查询它。教学阶段这个取舍划算。

catalog 的变更（建表、建索引、根页变化、堆链增长）必须与数据页
**在同一次提交里**落盘，否则崩溃后会出现「表头说有 3 页、实际只有 2 页」
的撕裂状态。所以 catalog 页也走 Pager 的脏页集，与其它页一起进 WAL。
"""

from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass, field
from typing import Optional

from .errors import SchemaError, StorageError
from .pager import PAGE_CATALOG, PAGE_SIZE, Pager

# catalog 页头：type(1) next(8) length(4) = 13 字节
_HDR = struct.Struct(">BQI")
_CHUNK = PAGE_SIZE - _HDR.size


@dataclass
class Column:
    """一列的定义。"""

    name: str
    col_type: str  # INT / TEXT / FLOAT（codec 规范化后的名字）
    primary_key: bool = False
    not_null: bool = False


@dataclass
class IndexInfo:
    """一个索引：B+ 树根页 + 索引列（列名存规范名）。"""

    name: str
    table: str
    columns: list[str]
    root_page: int
    unique: bool = False
    primary: bool = False  # 主键索引由 CREATE TABLE 自动创建，.schema 不重复展示


@dataclass
class TableInfo:
    """一张表的完整描述。"""

    name: str
    columns: list[Column]
    first_page: int
    last_page: int
    indexes: list[IndexInfo] = field(default_factory=list)

    def column_index(self, name: str) -> int:
        """列名 -> 下标（大小写不敏感）。找不到抛 SchemaError。"""
        low = name.lower()
        for i, col in enumerate(self.columns):
            if col.name.lower() == low:
                return i
        raise SchemaError(f"表 {self.name} 中不存在列: {name}")

    @property
    def pk_columns(self) -> list[Column]:
        return [c for c in self.columns if c.primary_key]

    @property
    def pk_index(self) -> Optional[IndexInfo]:
        for idx in self.indexes:
            if idx.primary:
                return idx
        return None

    def find_index(self, name: str) -> Optional[IndexInfo]:
        low = name.lower()
        for idx in self.indexes:
            if idx.name.lower() == low:
                return idx
        return None


def table_ddl(info: TableInfo) -> str:
    """从元数据反向生成 CREATE TABLE 语句（供 .schema 使用）。"""
    lines = []
    for col in info.columns:
        parts = [col.name, col.col_type]
        if col.primary_key:
            parts.append("PRIMARY KEY")
        elif col.not_null:
            parts.append("NOT NULL")
        lines.append("  " + " ".join(parts))
    return f"CREATE TABLE {info.name} (\n" + ",\n".join(lines) + "\n);"


def index_ddl(info: IndexInfo) -> str:
    unique = "UNIQUE " if info.unique else ""
    cols = ", ".join(info.columns)
    return f"CREATE {unique}INDEX {info.name} ON {info.table} ({cols});"


class Catalog:
    """catalog 的内存镜像 + 页链持久化。"""

    def __init__(self, pager: Pager) -> None:
        self.pager = pager
        self.tables: dict[str, TableInfo] = {}
        self.dirty = False

    # -- 持久化 -------------------------------------------------------------

    def load(self) -> None:
        """从页链读回 JSON。catalog_start=0 表示空库。"""
        self.tables = {}
        page = self.pager.catalog_start
        if not page:
            return
        blob = bytearray()
        while page:
            buf = self.pager.read(page)
            ptype, nxt, length = _HDR.unpack_from(buf, 0)
            if ptype != PAGE_CATALOG:
                raise StorageError(f"catalog 页类型错误: {page}")
            blob += buf[_HDR.size : _HDR.size + length]
            page = nxt
        try:
            obj = json.loads(bytes(blob).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StorageError(f"catalog 损坏: {exc}") from exc
        for name, t in obj.get("tables", {}).items():
            columns = [Column(**c) for c in t["columns"]]
            indexes = [IndexInfo(**i) for i in t.get("indexes", [])]
            self.tables[name] = TableInfo(
                name=t["name"], columns=columns,
                first_page=t["first_page"], last_page=t["last_page"],
                indexes=indexes,
            )
        self.dirty = False

    def save(self) -> None:
        """把内存镜像写回页链：先释放旧链，再分配新链。"""
        payload = json.dumps(
            {"version": 1, "tables": {n: asdict(t) for n, t in self.tables.items()}},
            ensure_ascii=False,
        ).encode("utf-8")

        # 释放旧链（先取 next 再 free，否则指针被覆盖）
        page = self.pager.catalog_start
        while page:
            nxt = _HDR.unpack_from(self.pager.read(page), 0)[1]
            self.pager.free(page)
            page = nxt

        chunks = [payload[i : i + _CHUNK] for i in range(0, len(payload), _CHUNK)] or [b""]
        pages = [self.pager.allocate() for _ in chunks]
        for i, (pg, chunk) in enumerate(zip(pages, chunks)):
            buf = self.pager.buffer(pg)
            buf[:] = bytes(PAGE_SIZE)
            nxt = pages[i + 1] if i + 1 < len(pages) else 0
            _HDR.pack_into(buf, 0, PAGE_CATALOG, nxt, len(chunk))
            buf[_HDR.size : _HDR.size + len(chunk)] = chunk
        self.pager.catalog_start = pages[0]
        self.dirty = False

    def touch(self) -> None:
        """结构发生变化（根页、堆链增长等），标记需要在提交时落盘。"""
        self.dirty = True

    # -- 查询 / 变更 --------------------------------------------------------

    def find_table(self, name: str) -> Optional[TableInfo]:
        low = name.lower()
        for tname, info in self.tables.items():
            if tname.lower() == low:
                return info
        return None

    def require_table(self, name: str) -> TableInfo:
        info = self.find_table(name)
        if info is None:
            raise SchemaError(f"表不存在: {name}")
        return info

    def add_table(self, info: TableInfo) -> None:
        if self.find_table(info.name) is not None:
            raise SchemaError(f"表已存在: {info.name}")
        self.tables[info.name] = info
        self.touch()

    def index_name_available(self, name: str) -> bool:
        low = name.lower()
        if any(t.find_index(low) for t in self.tables.values()):
            return False
        return not any(n.lower() == low for n in self.tables)

    def ddl_for(self, table: str) -> list[str]:
        """某张表的全部 DDL 语句（CREATE TABLE + 各 CREATE INDEX）。"""
        info = self.require_table(table)
        stmts = [table_ddl(info)]
        stmts += [index_ddl(i) for i in info.indexes if not i.primary]
        return stmts

    def all_ddl(self) -> list[str]:
        stmts = []
        for name in self.tables:
            stmts += self.ddl_for(name)
        return stmts
