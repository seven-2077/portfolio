"""Volcano 迭代器模型 —— 每个算子实现 ``open / next / close`` 三件套。

这是数据库执行器最经典的接口（Goetz Graefe, 1994）：

* ``open()``  初始化扫描状态；
* ``next()``  产出**一行**（没有了返回 None）—— 惰性求值的核心；
* ``close()`` 释放游标与文件句柄。

所有算子串成一棵树，根节点被反复 ``next()``，数据自底向上流动。
好处是不需要把中间结果物化成临时表 —— ``SELECT ... LIMIT 10``
只真正取 10 行就短路了。

设计上的两个刻意选择：

1. **所有算子统一产出** ``Row(rowid, values)``。rowid 对 SELECT 无感，
   但 UPDATE/DELETE 必须知道「这行在哪个页哪个槽」才能回写；
   统一类型让算子接口只有一种形状。
2. **DML 算子在 open() 里先物化匹配行**，再在 next() 里动手改。
   为什么？顺序扫描是游标式的，若边扫边改，UPDATE 把行搬到最后一页时
   游标还没走到那里，同一行会被扫到两次（``SET x = x+1`` 就加了两次）。
   物化相当于拿到了「行的快照」—— 这正是 MVCC 快照读的雏形，
   完整的 MVCC 列在 Roadmap。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import cmp_to_key
from typing import Iterator, NamedTuple, Optional

from .ast import Expr, OrderItem, eval_expr, format_expr
from .codec import compare_values
from .table import Table


class Row(NamedTuple):
    """一行数据：rowid（行标识）+ 各列值。"""

    rowid: int
    values: tuple


class Operator(ABC):
    """所有算子的基类。"""

    schema: list[str] = []

    def __init__(self, children: list["Operator"]) -> None:
        self.children = children

    def open(self) -> None:
        for child in self.children:
            child.open()

    @abstractmethod
    def next(self) -> Optional[Row]:
        """产出下一行；耗尽返回 None。"""

    def close(self) -> None:
        for child in self.children:
            child.close()

    def describe(self) -> str:
        """EXPLAIN 里显示的单行节点名。"""
        return type(self).__name__

    def rowcount(self) -> int:
        """受影响行数（DML 算子覆写）。"""
        return 0


def render_plan(root: Operator) -> list[str]:
    """把算子树画成缩进树（EXPLAIN 的输出）。"""
    lines: list[str] = []

    def walk(node: Operator, prefix: str, is_last: bool, is_root: bool) -> None:
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        lines.append(prefix + connector + node.describe())
        child_prefix = prefix + ("" if is_root else ("   " if is_last else "│  "))
        kids = node.children
        for i, child in enumerate(kids):
            walk(child, child_prefix, i == len(kids) - 1, False)

    walk(root, "", True, True)
    return lines


def _env_of(schema: list[str]) -> dict[str, int]:
    """列环境：列名小写 -> 下标（AST 里的列名已小写化）。"""
    return {name.lower(): i for i, name in enumerate(schema)}


class SeqScan(Operator):
    """全表顺序扫描：顺堆页链逐页逐槽取行。"""

    def __init__(self, table: Table) -> None:
        super().__init__([])
        self.table = table
        self.schema = table.column_names
        self._iter: Optional[Iterator[tuple[int, tuple]]] = None

    def open(self) -> None:
        self._iter = self.table.scan()

    def next(self) -> Optional[Row]:
        if self._iter is None:
            return None
        try:
            return Row(*next(self._iter))
        except StopIteration:
            return None

    def close(self) -> None:
        if self._iter is not None:
            self._iter.close()

    def describe(self) -> str:
        return f"SeqScan({self.table.name})"


class IndexScan(Operator):
    """索引扫描：按复合键前缀或键范围取行，顺叶子链有序产出。"""

    def __init__(
        self,
        table: Table,
        index,
        lo: bytes | None = None,
        hi: bytes | None = None,
        lo_inclusive: bool = True,
        hi_inclusive: bool = True,
        prefix: bytes | None = None,
        desc: str = "",
    ) -> None:
        super().__init__([])
        self.table = table
        self.index = index
        self.lo = lo
        self.hi = hi
        self.lo_inclusive = lo_inclusive
        self.hi_inclusive = hi_inclusive
        self.prefix = prefix
        self.desc = desc
        self.schema = table.column_names
        self._iter: Optional[Iterator[tuple[int, tuple]]] = None

    def open(self) -> None:
        if self.prefix is not None:
            self._iter = self.table.prefix_scan(self.index, self.prefix)
        else:
            self._iter = self.table.index_scan(
                self.index,
                start=self.lo,
                end=self.hi,
                start_inclusive=self.lo_inclusive,
                end_inclusive=self.hi_inclusive,
            )

    def next(self) -> Optional[Row]:
        if self._iter is None:
            return None
        try:
            return Row(*next(self._iter))
        except StopIteration:
            return None

    def close(self) -> None:
        if self._iter is not None:
            self._iter.close()

    def describe(self) -> str:
        name = self.index.info.name
        return f"IndexScan({self.table.name} USING {name}, {self.desc})"


class ValuesScan(Operator):
    """VALUES 行集扫描（INSERT 的数据源）。"""

    def __init__(self, rows: list[tuple]) -> None:
        super().__init__([])
        self.rows = rows
        self.schema: list[str] = []
        self._iter: Optional[Iterator[tuple]] = None

    def open(self) -> None:
        self._iter = iter(self.rows)

    def next(self) -> Optional[Row]:
        if self._iter is None:
            return None
        try:
            return Row(-1, next(self._iter))
        except StopIteration:
            return None

    def describe(self) -> str:
        return f"Values({len(self.rows)} rows)"


class Filter(Operator):
    """过滤：谓词为假或 NULL 的行被丢弃（NULL 当假，SQL 语义）。"""

    def __init__(self, child: Operator, predicate: Expr) -> None:
        super().__init__([child])
        self.child = child
        self.predicate = predicate
        self.schema = child.schema
        self._env = _env_of(child.schema)

    def next(self) -> Optional[Row]:
        while True:
            row = self.child.next()
            if row is None:
                return None
            if eval_expr(self.predicate, self._env, row.values):
                return row

    def describe(self) -> str:
        return f"Filter({format_expr(self.predicate)})"


class Project(Operator):
    """投影：按 SELECT 列表求值产出新行（同时决定输出列名）。"""

    def __init__(self, child: Operator, items: list[tuple[Expr, str]]) -> None:
        super().__init__([child])
        self.child = child
        self.items = items
        self.schema = [name for _expr, name in items]
        self._env = _env_of(child.schema)

    def next(self) -> Optional[Row]:
        row = self.child.next()
        if row is None:
            return None
        values = tuple(eval_expr(expr, self._env, row.values) for expr, _name in self.items)
        return Row(row.rowid, values)

    def describe(self) -> str:
        return f"Project({', '.join(self.schema)})"


class Sort(Operator):
    """排序：open 时一次性物化再排序（内存排序，外部归并列入 Roadmap）。"""

    def __init__(self, child: Operator, keys: list[OrderItem]) -> None:
        super().__init__([child])
        self.child = child
        self.keys = keys
        self.schema = child.schema
        self._env = _env_of(child.schema)
        self._iter: Optional[Iterator[Row]] = None

    def open(self) -> None:
        self.child.open()
        rows: list[tuple[Row, tuple]] = []
        while True:
            row = self.child.next()
            if row is None:
                break
            rows.append((row, tuple(eval_expr(k.expr, self._env, row.values) for k in self.keys)))
        self.child.close()

        directions = [1 if k.ascending else -1 for k in self.keys]

        def compare(a, b) -> int:
            for x, y, d in zip(a[1], b[1], directions):
                c = compare_values(x, y)  # NULL 最小、跨类型报错，与 WHERE 共用一套语义
                if c:
                    return c * d
            return 0

        rows.sort(key=cmp_to_key(compare))
        self._iter = iter([r for r, _k in rows])

    def next(self) -> Optional[Row]:
        if self._iter is None:
            return None
        try:
            return next(self._iter)
        except StopIteration:
            return None

    def describe(self) -> str:
        parts = [f"{format_expr(k.expr)} {'ASC' if k.ascending else 'DESC'}" for k in self.keys]
        return f"Sort({', '.join(parts)})"


class _AggState:
    """单个聚合函数的累加器。"""

    __slots__ = ("func", "total", "count", "best")

    def __init__(self, func: str) -> None:
        self.func = func
        self.total = None   # SUM / AVG 的和
        self.count = 0      # COUNT / AVG 的计数
        self.best = None    # MIN / MAX 的当前最优

    def add(self, value) -> None:
        if value is None:
            return  # 聚合函数一律忽略 NULL
        if self.func in ("COUNT", "AVG"):
            self.count += 1
        if self.func in ("SUM", "AVG"):
            self.total = value if self.total is None else self.total + value
        if self.func in ("MIN", "MAX"):
            if self.best is None:
                self.best = value
            else:
                c = compare_values(value, self.best)
                if (self.func == "MIN" and c < 0) or (self.func == "MAX" and c > 0):
                    self.best = value

    def finish(self):
        if self.func == "COUNT":
            return self.count
        if self.func == "SUM":
            return self.total
        if self.func == "AVG":
            return None if self.count == 0 else self.total / self.count
        return self.best  # MIN / MAX：一个都没见到就是 NULL


class Aggregate(Operator):
    """哈希聚合：按 GROUP BY 键分桶，桶内累加各聚合函数。

    用 dict 分桶是「以空间换时间」的经典做法（408 里的散列表应用）。
    分组保持**首次出现顺序**，让输出可预期；需要别的顺序由上层 Sort 决定。
    没有 GROUP BY 且输入为空时，仍要产出一行
    （``SELECT COUNT(*) FROM empty`` 得 0 而不是空集 —— SQL 标准）。
    """

    def __init__(
        self,
        child: Operator,
        group_exprs: list[Expr],
        specs: list[tuple[str, Optional[Expr], str]],  # (函数名, 参数, 输出名)
        group_names: list[str],
    ) -> None:
        super().__init__([child])
        self.child = child
        self.group_exprs = group_exprs
        self.specs = specs
        self.schema = group_names + [name for _f, _a, name in specs]
        self._env = _env_of(child.schema)
        self._groups: dict[tuple, list[_AggState]] = {}
        self._order: list[tuple] = []
        self._iter: Optional[Iterator[Row]] = None

    def open(self) -> None:
        self._groups = {}
        self._order = []
        self.child.open()
        while True:
            row = self.child.next()
            if row is None:
                break
            key = tuple(eval_expr(g, self._env, row.values) for g in self.group_exprs)
            states = self._groups.get(key)
            if states is None:
                states = [_AggState(func) for func, _a, _n in self.specs]
                self._groups[key] = states
                self._order.append(key)
            for state, (func, arg, _name) in zip(states, self.specs):
                if arg is None:
                    # COUNT(*)：参数缺省，计的是「行数本身」。
                    # 必须传非 None 的哨兵 —— add() 会跳过 NULL，
                    # 直接传 None 会让 COUNT(*) 永远是 0（联调时踩过）。
                    value = 1 if func == "COUNT" else None
                else:
                    value = eval_expr(arg, self._env, row.values)
                state.add(value)
        self.child.close()

        if not self._groups and not self.group_exprs:
            # 空表 + 无分组：仍然是一组（COUNT=0，其余 NULL）
            self._groups[()] = [_AggState(func) for func, _a, _n in self.specs]
            self._order.append(())

        rows = []
        for key in self._order:
            states = self._groups[key]
            rows.append(Row(-1, key + tuple(s.finish() for s in states)))
        self._iter = iter(rows)

    def next(self) -> Optional[Row]:
        if self._iter is None:
            return None
        try:
            return next(self._iter)
        except StopIteration:
            return None

    def describe(self) -> str:
        groups = ", ".join(self.schema[: len(self.group_exprs)]) or "（无）"
        aggs = ", ".join(name for _f, _a, name in self.specs)
        return f"Aggregate(group=[{groups}], aggs=[{aggs}])"


class Limit(Operator):
    """LIMIT / OFFSET：先跳过 offset 行，再最多产出 limit 行。"""

    def __init__(self, child: Operator, limit: Optional[int], offset: int) -> None:
        super().__init__([child])
        self.child = child
        self.limit = limit
        self.offset = offset
        self.schema = child.schema
        self._emitted = 0

    def open(self) -> None:
        self.child.open()
        self._emitted = 0
        skipped = 0
        while skipped < self.offset:
            if self.child.next() is None:
                break
            skipped += 1

    def next(self) -> Optional[Row]:
        if self.limit is not None and self._emitted >= self.limit:
            return None
        row = self.child.next()
        if row is None:
            return None
        self._emitted += 1
        return row

    def describe(self) -> str:
        if self.offset:
            return f"Limit({self.limit} OFFSET {self.offset})"
        return f"Limit({self.limit})"


class InsertOp(Operator):
    """INSERT：逐行把子节点产出的值写进表。"""

    def __init__(self, table: Table, child: Operator) -> None:
        super().__init__([child])
        self.table = table
        self.child = child
        self.schema: list[str] = []
        self._count = 0
        self._done = False

    def next(self) -> Optional[Row]:
        if self._done:
            return None
        self._done = True
        while True:
            row = self.child.next()
            if row is None:
                break
            self.table.insert(list(row.values))
            self._count += 1
        return None

    def rowcount(self) -> int:
        return self._count

    def describe(self) -> str:
        return f"Insert({self.table.name})"


class UpdateOp(Operator):
    """UPDATE：先物化匹配行，再逐行求新值、回写、修索引。"""

    def __init__(self, table: Table, assignments: list[tuple[int, Expr]], child: Operator) -> None:
        super().__init__([child])
        self.table = table
        self.assignments = assignments
        self.child = child
        self.schema: list[str] = []
        self._env = _env_of(child.schema)
        self._rows: list[Row] = []
        self._count = 0
        self._done = False

    def open(self) -> None:
        # 物化：拿到匹配行的快照后再改，避免游标踩到自己搬走的行
        self.child.open()
        self._rows = []
        while True:
            row = self.child.next()
            if row is None:
                break
            self._rows.append(row)
        self.child.close()

    def next(self) -> Optional[Row]:
        if self._done:
            return None
        self._done = True
        for row in self._rows:
            new_values = list(row.values)
            # 所有新值都基于**旧**行求值（SET a = b, b = a 才不会串味）
            for pos, expr in self.assignments:
                new_values[pos] = eval_expr(expr, self._env, row.values)
            self.table.update(row.rowid, row.values, tuple(new_values))
            self._count += 1
        return None

    def rowcount(self) -> int:
        return self._count

    def describe(self) -> str:
        sets = ", ".join(
            f"{self.table.info.columns[pos].name} = {format_expr(expr)}"
            for pos, expr in self.assignments
        )
        return f"Update({self.table.name} SET {sets})"


class DeleteOp(Operator):
    """DELETE：先物化匹配行，再逐行摘索引、打墓碑。"""

    def __init__(self, table: Table, child: Operator) -> None:
        super().__init__([child])
        self.table = table
        self.child = child
        self.schema: list[str] = []
        self._rows: list[Row] = []
        self._count = 0
        self._done = False

    def open(self) -> None:
        self.child.open()
        self._rows = []
        while True:
            row = self.child.next()
            if row is None:
                break
            self._rows.append(row)
        self.child.close()

    def next(self) -> Optional[Row]:
        if self._done:
            return None
        self._done = True
        for row in self._rows:
            self.table.delete(row.rowid, row.values)
            self._count += 1
        return None

    def rowcount(self) -> int:
        return self._count

    def describe(self) -> str:
        return f"Delete({self.table.name})"


class DDLPlan(Operator):
    """DDL 的占位节点：EXPLAIN CREATE TABLE 之类只展示、不执行。"""

    def __init__(self, label: str) -> None:
        super().__init__([])
        self.label = label
        self.schema: list[str] = []

    def next(self) -> Optional[Row]:
        return None

    def describe(self) -> str:
        return self.label
