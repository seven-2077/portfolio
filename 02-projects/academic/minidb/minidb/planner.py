"""查询规划器：AST -> 物理算子树（access path 选择 + 校验）。

规划器做三件事：

1. **语义校验**：未知列、未知函数、聚合放错位置（WHERE 里）、
   非分组列出现在 SELECT —— 全部在**动手执行前**报错。
2. **存取路径选择**（access path）：SeqScan 还是 IndexScan？
   规则刻意保持简单可解释（没有统计信息，也就没有代价模型）：

   a. WHERE 里有主键的等值/范围 -> 主键索引（顺带消费掉这些合取项）；
   b. 否则，WHERE 里有某二级索引**最左前缀**的等值 -> 该索引前缀扫描；
   c. 否则，ORDER BY 恰好是主键升序 -> 主键索引顺序扫，省掉 Sort；
   d. 其余 -> 全表顺序扫描。

   被索引「消费」的合取项不再进 Filter（计划更干净），
   其余合取项原样保留 —— 索引给候选行，Filter 兜底保正确。
3. **组装算子树**：Scan -> Filter -> Aggregate? -> Sort? -> Project -> Limit。

聚合路径上有一个容易踩的坑：ORDER BY 里的 ``COUNT(*)`` 必须被**改写**
成对 Aggregate 输出列的引用（:func:`_rewrite_agg_ref`），
否则 Sort 会试图在原始行上求值聚合函数 —— 那时它早已被聚合掉了。
"""

from __future__ import annotations

from typing import Optional

from .ast import (
    Binary,
    Column,
    CreateIndex,
    CreateTable,
    Delete,
    Explain,
    Expr,
    FuncCall,
    Insert,
    Literal,
    OrderItem,
    Select,
    SelectItem,
    Statement,
    Update,
    and_all,
    format_expr,
    has_aggregate,
    split_and,
    walk,
)
from .catalog import Catalog, Column as ColumnDef, IndexInfo, TableInfo
from .codec import decode_key, encode_key
from .errors import MiniDBError, SchemaError, StorageError, TypeMismatchError
from .operators import (
    Aggregate,
    DeleteOp,
    Filter,
    IndexScan,
    InsertOp,
    Limit,
    Operator,
    Project,
    SeqScan,
    Sort,
    UpdateOp,
    ValuesScan,
    render_plan,
)
from .pager import Pager
from .table import Index, Table, resolve_columns


def _tighter_lo(cur, cand):
    """收紧下界：取更大的键；同键取更严的包含性。"""
    if cur is None:
        return cand
    if cand[0] > cur[0]:
        return cand
    if cand[0] == cur[0]:
        return (cur[0], cur[1] and cand[1])
    return cur


def _tighter_hi(cur, cand):
    """收紧上界：取更小的键；同键取更严的包含性。"""
    if cur is None:
        return cand
    if cand[0] < cur[0]:
        return cand
    if cand[0] == cur[0]:
        return (cur[0], cur[1] and cand[1])
    return cur


class Planner:
    """把语句编译成算子树。planner 本身无状态，可每条语句新建。"""

    def __init__(self, catalog: Catalog, pager: Pager) -> None:
        self.catalog = catalog
        self.pager = pager

    # -- 基础工具 -----------------------------------------------------------

    def _table(self, name: str) -> tuple[Table, TableInfo]:
        info = self.catalog.require_table(name)
        return Table(self.pager, info, self.catalog), info

    @staticmethod
    def _index_of(table: Table, idx_info: IndexInfo) -> Index:
        for idx in table.indexes:
            if idx.info is idx_info:
                return idx
        raise SchemaError(f"索引不存在: {idx_info.name}")

    @staticmethod
    def _check_functions(expr: Expr, allow_agg: bool, clause: str) -> None:
        for node in walk(expr):
            if not isinstance(node, FuncCall):
                continue
            if node.name not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
                raise MiniDBError(
                    f"未知函数 {node.name}()；MiniDB 支持 COUNT / SUM / AVG / MIN / MAX"
                )
            if not allow_agg:
                raise MiniDBError(f"{clause}子句中不能使用聚合函数")
            Planner._validate_agg(node)

    @staticmethod
    def _validate_agg(fc: FuncCall) -> None:
        if fc.name == "COUNT":
            if not fc.star and len(fc.args) != 1:
                raise MiniDBError("COUNT 需要写成 COUNT(*) 或 COUNT(表达式)")
        else:
            if fc.star:
                raise MiniDBError(f"{fc.name}() 不支持 *，需要一个表达式参数")
            if len(fc.args) != 1:
                raise MiniDBError(f"{fc.name}() 恰好需要 1 个参数")
        if any(has_aggregate(arg) for arg in fc.args):
            raise MiniDBError("聚合函数不能嵌套")

    @staticmethod
    def _check_columns(expr: Expr, info: TableInfo, clause: str) -> None:
        for node in walk(expr):
            if isinstance(node, Column):
                info.column_index(node.name)  # 不存在会抛 SchemaError（带列名）

    @staticmethod
    def _default_name(expr: Expr, info: TableInfo) -> str:
        """输出列名：简单列用表里的规范名（保留用户建表时的大小写）。"""
        if isinstance(expr, Column):
            pos = info.column_index(expr.name)
            return info.columns[pos].name
        return format_expr(expr)

    # -- 存取路径选择 -------------------------------------------------------

    @staticmethod
    def _lit_key(value, col_type: str, col_name: str) -> bytes:
        """把字面量按主键类型编码成索引键（类型不符立即报错）。"""
        if col_type == "INT" and isinstance(value, float) and value.is_integer():
            value = int(value)
        elif col_type == "FLOAT" and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        try:
            return encode_key(value, col_type)
        except (TypeMismatchError, StorageError) as exc:
            raise TypeMismatchError(
                f"条件与 {col_name}({col_type}) 类型不匹配: {value!r}"
            ) from exc

    def _pk_bounds(self, conjuncts: list[Expr], info: TableInfo):
        """从合取项里榨出主键的上下界。返回 (lo, hi, consumed) 或 None。

        lo/hi 形如 (键字节, 是否含边界)；同一侧多个条件取最紧的。
        ``5 = id`` 这种字面量在左的写法会先翻转运算符再处理。
        """
        pk_cols = info.pk_columns
        if len(pk_cols) != 1:
            return None
        pk = pk_cols[0]
        pk_name = pk.name.lower()
        lo = hi = None
        consumed: list[Expr] = []
        flip = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "=": "="}
        for c in conjuncts:
            if not isinstance(c, Binary) or c.op not in ("=", "<", "<=", ">", ">="):
                continue
            op = c.op
            lit: Optional[Literal] = None
            if isinstance(c.left, Column) and c.left.name == pk_name and isinstance(c.right, Literal):
                lit = c.right
            elif isinstance(c.right, Column) and c.right.name == pk_name and isinstance(c.left, Literal):
                lit = c.left
                op = flip[op]
            if lit is None:
                continue
            key = self._lit_key(lit.value, pk.col_type, pk.name)
            consumed.append(c)
            if op == "=":
                lo = _tighter_lo(lo, (key, True))
                hi = _tighter_hi(hi, (key, True))
            elif op == ">":
                lo = _tighter_lo(lo, (key, False))
            elif op == ">=":
                lo = _tighter_lo(lo, (key, True))
            elif op == "<":
                hi = _tighter_hi(hi, (key, False))
            else:  # <=
                hi = _tighter_hi(hi, (key, True))
        if not consumed:
            return None
        return lo, hi, consumed

    @staticmethod
    def _order_is_pk_asc(order_by: list[OrderItem], info: TableInfo) -> bool:
        """ORDER BY 是否恰好是「主键各列升序」？是则索引天然有序，免 Sort。"""
        pk = info.pk_columns
        if not pk or len(order_by) != len(pk):
            return False
        for item, col in zip(order_by, pk):
            if not item.ascending:
                return False
            if not (isinstance(item.expr, Column) and item.expr.name == col.name.lower()):
                return False
        return True

    @staticmethod
    def _find_equality(conjuncts: list[Expr], used: list[Expr], col_name: str):
        """在还没被消费的合取项里找 ``col = 字面量``。"""
        low = col_name.lower()
        for c in conjuncts:
            if any(c is u for u in used):
                continue
            if not isinstance(c, Binary) or c.op != "=":
                continue
            if isinstance(c.left, Column) and c.left.name == low and isinstance(c.right, Literal):
                return c, c.right.value
            if isinstance(c.right, Column) and c.right.name == low and isinstance(c.left, Literal):
                return c, c.left.value
        return None

    @staticmethod
    def _bounds_desc(name: str, col_type: str, lo, hi) -> str:
        if lo is not None and hi is not None and lo[0] == hi[0] and lo[1] and hi[1]:
            return f"{name} = {format_expr(Literal(decode_key(lo[0], col_type)))}"
        parts = []
        if lo is not None:
            v = decode_key(lo[0], col_type)
            parts.append(f"{name} {'>=' if lo[1] else '>'} {format_expr(Literal(v))}")
        if hi is not None:
            v = decode_key(hi[0], col_type)
            parts.append(f"{name} {'<=' if hi[1] else '<'} {format_expr(Literal(v))}")
        return " AND ".join(parts)

    def _build_scan(
        self, table: Table, conjuncts: list[Expr], order_by: list[OrderItem]
    ) -> tuple[Operator, list[Expr], bool]:
        """返回 (扫描算子, 剩余过滤项, 输出是否已按 ORDER BY 有序)。"""
        info = table.info
        pk_idx = info.pk_index

        # a. 主键等值 / 范围
        if pk_idx is not None:
            bounds = self._pk_bounds(conjuncts, info)
            if bounds is not None:
                lo, hi, consumed = bounds
                pk = info.pk_columns[0]
                scan = IndexScan(
                    table,
                    self._index_of(table, pk_idx),
                    lo=None if lo is None else lo[0],
                    hi=None if hi is None else hi[0],
                    lo_inclusive=True if lo is None else lo[1],
                    hi_inclusive=True if hi is None else hi[1],
                    desc=self._bounds_desc(pk.name, pk.col_type, lo, hi),
                )
                residual = [c for c in conjuncts if not any(c is x for x in consumed)]
                return scan, residual, self._order_is_pk_asc(order_by, info)

        # b. 二级索引最左前缀等值
        for idx_info in info.indexes:
            if idx_info.primary:
                continue
            idx = self._index_of(table, idx_info)
            used: list[Expr] = []
            by_col: dict[str, object] = {}
            for col_name in idx_info.columns:
                found = self._find_equality(conjuncts, used, col_name)
                if found is None:
                    break
                used.append(found[0])
                by_col[col_name.lower()] = found[1]
            if not used:
                continue
            prefix = idx.prefix_for(by_col)
            if prefix is None:
                continue
            desc = " AND ".join(format_expr(c) for c in used)
            scan = IndexScan(table, idx, prefix=prefix, desc=desc)
            residual = [c for c in conjuncts if not any(c is x for x in used)]
            return scan, residual, False

        # c. ORDER BY 主键 -> 主键索引顺序扫
        if pk_idx is not None and self._order_is_pk_asc(order_by, info):
            pk = info.pk_columns[0]
            scan = IndexScan(
                table, self._index_of(table, pk_idx), desc=f"{pk.name} 按序全扫"
            )
            return scan, conjuncts, True

        # d. 兜底：全表顺序扫描
        return SeqScan(table), conjuncts, False

    # -- 各语句的编译 -------------------------------------------------------

    def build(self, stmt: Statement) -> tuple[Operator, list[str]]:
        if isinstance(stmt, Select):
            return self._build_select(stmt)
        if isinstance(stmt, Insert):
            return self._build_insert(stmt)
        if isinstance(stmt, Update):
            return self._build_update(stmt)
        if isinstance(stmt, Delete):
            return self._build_delete(stmt)
        raise MiniDBError("DDL 语句不产生执行计划（EXPLAIN 除外）")

    def _build_select(self, s: Select) -> tuple[Operator, list[str]]:
        table, info = self._table(s.table)
        items = s.items
        if s.star:
            items = [SelectItem(Column(c.name.lower())) for c in info.columns]

        # 1) 语义校验（全部前置，出错时还没碰任何存储）
        if s.where is not None:
            self._check_functions(s.where, False, "WHERE")
            self._check_columns(s.where, info, "WHERE")
        for item in items:
            self._check_functions(item.expr, True, "SELECT")
            self._check_columns(item.expr, info, "SELECT")
        for g in s.group_by:
            self._check_functions(g, False, "GROUP BY")
            self._check_columns(g, info, "GROUP BY")
        for o in s.order_by:
            self._check_functions(o.expr, True, "ORDER BY")
            self._check_columns(o.expr, info, "ORDER BY")

        is_agg = (
            bool(s.group_by)
            or any(has_aggregate(i.expr) for i in items)
            or any(has_aggregate(o.expr) for o in s.order_by)
        )
        if is_agg:
            return self._build_aggregate_select(s, items, table, info)
        return self._build_plain_select(s, items, table, info)

    def _build_plain_select(
        self, s: Select, items: list[SelectItem], table: Table, info: TableInfo
    ) -> tuple[Operator, list[str]]:
        conjuncts = split_and(s.where)
        scan, residual, ordered = self._build_scan(table, conjuncts, s.order_by)

        node: Operator = scan
        if residual:
            node = Filter(node, and_all(residual))
        if s.order_by and not ordered:
            node = Sort(node, s.order_by)

        out = [(item.expr, item.alias or self._default_name(item.expr, info)) for item in items]
        node = Project(node, out)
        if s.limit is not None or s.offset:
            node = Limit(node, s.limit, s.offset)
        return node, [name for _expr, name in out]

    def _build_aggregate_select(
        self, s: Select, items: list[SelectItem], table: Table, info: TableInfo
    ) -> tuple[Operator, list[str]]:
        # GROUP BY 键去重（同一表达式写两遍只分一桶）
        group_exprs: list[Expr] = []
        for g in s.group_by:
            if not any(g == x for x in group_exprs):
                group_exprs.append(g)
        group_names = [self._default_name(g, info) for g in group_exprs]

        # 收集聚合（SELECT 项与 ORDER BY 项都可能有，按打印名去重）
        aggs: list[FuncCall] = []
        agg_names: set[str] = set()

        def register(fc: FuncCall) -> None:
            name = format_expr(fc)
            if name not in agg_names:
                agg_names.add(name)
                aggs.append(fc)

        for item in items:
            if has_aggregate(item.expr):
                if not isinstance(item.expr, FuncCall):
                    raise MiniDBError(
                        "聚合函数只能作为独立的 SELECT 项（暂不支持 age + COUNT(*) 这类混合表达式）"
                    )
                register(item.expr)
        for o in s.order_by:
            if has_aggregate(o.expr):
                if not isinstance(o.expr, FuncCall):
                    raise MiniDBError("ORDER BY 中聚合函数必须独立出现")
                register(o.expr)

        # 非聚合的 SELECT 项必须能从分组键里取到（否则它对每组没有唯一值）
        for item in items:
            if has_aggregate(item.expr):
                continue
            if not any(item.expr == g for g in group_exprs):
                raise MiniDBError(
                    f"列 {format_expr(item.expr)} 既不是聚合，也不在 GROUP BY 中"
                )

        conjuncts = split_and(s.where)
        # 聚合路径不利用扫描顺序：哈希分组不保序，Sort 必须按聚合输出排
        scan, residual, _ordered = self._build_scan(table, conjuncts, [])

        node: Operator = scan
        if residual:
            node = Filter(node, and_all(residual))
        specs = [(fc.name, None if fc.star else fc.args[0], format_expr(fc)) for fc in aggs]
        node = Aggregate(node, group_exprs, specs, group_names)

        if s.order_by:
            rewritten = [
                OrderItem(self._rewrite_agg_ref(o.expr, group_exprs, group_names, agg_names),
                          o.ascending)
                for o in s.order_by
            ]
            node = Sort(node, rewritten)

        out: list[tuple[Expr, str]] = []
        for item in items:
            if has_aggregate(item.expr):
                src = format_expr(item.expr)
                name = item.alias or src
            else:
                idx = next(i for i, g in enumerate(group_exprs) if item.expr == g)
                src = group_names[idx]
                name = item.alias or self._default_name(item.expr, info)
            out.append((Column(src), name))
        node = Project(node, out)
        if s.limit is not None or s.offset:
            node = Limit(node, s.limit, s.offset)
        return node, [name for _expr, name in out]

    @staticmethod
    def _rewrite_agg_ref(
        expr: Expr, group_exprs: list[Expr], group_names: list[str], agg_names: set[str]
    ) -> Column:
        """把 ORDER BY 表达式改写成对 Aggregate 输出列的引用。

        Sort 排在 Aggregate **之上**，它的输入行里已经没有原始列了 ——
        ``COUNT(*)`` 必须换成同名输出列，``dept`` 必须换成对应分组列。
        """
        if isinstance(expr, FuncCall):
            name = format_expr(expr)
            if name in agg_names:
                return Column(name)
            raise MiniDBError(f"ORDER BY 中的聚合 {name} 无法解析")
        for g, gname in zip(group_exprs, group_names):
            if expr == g:
                return Column(gname)
        raise MiniDBError(
            f"ORDER BY 表达式 {format_expr(expr)} 必须是聚合函数或出现在 GROUP BY 中"
        )

    def _build_insert(self, s: Insert) -> tuple[Operator, list[str]]:
        table, info = self._table(s.table)
        positions = resolve_columns(info, s.columns) if s.columns is not None else list(
            range(len(info.columns))
        )
        rows: list[tuple] = []
        for exprs in s.rows:
            if len(exprs) != len(positions):
                raise SchemaError(
                    f"VALUES 列数不匹配：期望 {len(positions)}，实际 {len(exprs)}"
                )
            full: list = [None] * len(info.columns)
            for expr, pos in zip(exprs, positions):
                self._check_functions(expr, False, "VALUES")
                # 空列环境：表达式里出现列名会以「未知列」报错
                full[pos] = eval_insert_expr(expr)
            rows.append(tuple(full))
        if not rows:
            raise SchemaError("INSERT 至少需要一行 VALUES")
        return InsertOp(table, ValuesScan(rows)), []

    def _build_update(self, s: Update) -> tuple[Operator, list[str]]:
        table, info = self._table(s.table)
        assignments: list[tuple[int, Expr]] = []
        for col_name, expr in s.assignments:
            pos = info.column_index(col_name)  # 未知列 -> SchemaError
            self._check_functions(expr, False, "SET")
            self._check_columns(expr, info, "SET")
            assignments.append((pos, expr))
        if s.where is not None:
            self._check_functions(s.where, False, "WHERE")
            self._check_columns(s.where, info, "WHERE")
        conjuncts = split_and(s.where)
        scan, residual, _ordered = self._build_scan(table, conjuncts, [])
        node: Operator = Filter(scan, and_all(residual)) if residual else scan
        return UpdateOp(table, assignments, node), []

    def _build_delete(self, s: Delete) -> tuple[Operator, list[str]]:
        table, info = self._table(s.table)
        if s.where is not None:
            self._check_functions(s.where, False, "WHERE")
            self._check_columns(s.where, info, "WHERE")
        conjuncts = split_and(s.where)
        scan, residual, _ordered = self._build_scan(table, conjuncts, [])
        node: Operator = Filter(scan, and_all(residual)) if residual else scan
        return DeleteOp(table, node), []

    # -- EXPLAIN ------------------------------------------------------------

    def explain(self, stmt: Statement) -> list[str]:
        if isinstance(stmt, Explain):
            stmt = stmt.stmt
        if isinstance(stmt, CreateTable):
            return [f"CreateTable({stmt.name})"]
        if isinstance(stmt, CreateIndex):
            cols = ", ".join(stmt.columns)
            return [f"CreateIndex({stmt.name} ON {stmt.table} ({cols}))"]
        plan, _columns = self.build(stmt)
        return render_plan(plan)


def eval_insert_expr(expr: Expr):
    """在空环境下求值 INSERT 的 VALUES 表达式（只允许字面量与算术）。"""
    from .ast import eval_expr

    return eval_expr(expr, {}, ())
