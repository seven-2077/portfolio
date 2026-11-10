"""抽象语法树（AST）：语句节点 + 表达式求值 + 表达式格式化。

解析器负责「文本 -> 这些节点」，规划器负责「节点 -> 算子树」，
而本模块还承担两件跨模块的活：

* :func:`eval_expr` —— 表达式求值。实现 SQL 的**三值逻辑**
  （NULL 参与的 AND/OR 结果可能是 NULL，过滤时 NULL 视为假），
  这是 408 里没有但 SQL 必考的语义，也是很多 ORM 踩坑的地方。
* :func:`format_expr` —— 把表达式**反打印**回文本。
  EXPLAIN 的计划树、聚合的输出列名（``COUNT(*)``）都靠它，
  必要时按优先级补括号，保证打印结果重新解析还是一棵树。

运算符优先级（低 -> 高，与 SQL 标准一致）::

    OR < AND < NOT < 比较 < 加减 < 乘除取模 < 一元 < 原子
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .codec import compare_values
from .errors import MiniDBError, SchemaError, TypeMismatchError

# ---------------------------------------------------------------------------
# 表达式节点
# ---------------------------------------------------------------------------


@dataclass
class Expr:
    """表达式基类（仅作类型标记）。"""


@dataclass
class Literal(Expr):
    value: object  # int / float / str / None


@dataclass
class Column(Expr):
    name: str  # 解析时统一小写，比较/查找都免去大小写问题


@dataclass
class Binary(Expr):
    op: str  # OR AND = != <> < <= > >= + - * / % IS
    left: Expr
    right: Expr


@dataclass
class Unary(Expr):
    op: str  # NOT - +
    operand: Expr


@dataclass
class FuncCall(Expr):
    name: str  # 聚合函数名（大写）：COUNT/SUM/AVG/MIN/MAX
    args: list[Expr] = field(default_factory=list)
    star: bool = False  # COUNT(*)


AGGREGATE_FUNCTIONS = frozenset({"COUNT", "SUM", "AVG", "MIN", "MAX"})


# ---------------------------------------------------------------------------
# 语句节点
# ---------------------------------------------------------------------------


@dataclass
class ColumnDef:
    name: str        # 保留 CREATE 时的原始大小写
    col_type: str    # 规范化后的 INT / TEXT / FLOAT
    primary_key: bool = False
    not_null: bool = False


@dataclass
class CreateTable:
    name: str
    columns: list[ColumnDef]


@dataclass
class CreateIndex:
    name: str
    table: str       # 小写
    columns: list[str]  # 原始大小写，执行时解析为规范名
    unique: bool = False


@dataclass
class Insert:
    table: str       # 小写
    columns: Optional[list[str]]  # None = 按表列序；否则小写列名
    rows: list[list[Expr]]


@dataclass
class SelectItem:
    expr: Expr
    alias: Optional[str] = None


@dataclass
class OrderItem:
    expr: Expr
    ascending: bool = True


@dataclass
class Select:
    table: str       # 小写
    items: list[SelectItem]
    star: bool = False
    where: Optional[Expr] = None
    group_by: list[Expr] = field(default_factory=list)
    order_by: list[OrderItem] = field(default_factory=list)
    limit: Optional[int] = None
    offset: int = 0


@dataclass
class Delete:
    table: str
    where: Optional[Expr] = None


@dataclass
class Update:
    table: str
    assignments: list[tuple[str, Expr]]  # 列名小写 -> 新值表达式
    where: Optional[Expr] = None


@dataclass
class Explain:
    stmt: "Statement"


Statement = Union[CreateTable, CreateIndex, Insert, Select, Delete, Update, Explain]


# ---------------------------------------------------------------------------
# 结构工具
# ---------------------------------------------------------------------------

# 优先级表：数值越大绑得越紧
_BIN_PREC = {"OR": 1, "AND": 2, "=": 4, "!=": 4, "<>": 4, "<": 4, ">": 4, "<=": 4, ">=": 4,
             "IS": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}
_UNARY_PREC = 3      # NOT
_PRIMARY_PREC = 8


def split_and(expr: Optional[Expr]) -> list[Expr]:
    """把 WHERE 拆成 AND 连接的合取项列表（索引选择的基础操作）。"""
    if expr is None:
        return []
    if isinstance(expr, Binary) and expr.op == "AND":
        return split_and(expr.left) + split_and(expr.right)
    return [expr]


def and_all(items: list[Expr]) -> Optional[Expr]:
    """split_and 的逆操作。"""
    result: Optional[Expr] = None
    for item in items:
        result = item if result is None else Binary("AND", result, item)
    return result


def has_aggregate(expr: Expr) -> bool:
    """表达式里是否出现聚合函数（WHERE/INSERT 中出现即为语义错误）。"""
    if isinstance(expr, FuncCall):
        return True
    if isinstance(expr, Binary):
        return has_aggregate(expr.left) or has_aggregate(expr.right)
    if isinstance(expr, Unary):
        return has_aggregate(expr.operand)
    return False


def walk(expr: Expr):
    """深度优先产出表达式的所有节点（供校验遍历使用）。"""
    yield expr
    if isinstance(expr, Binary):
        yield from walk(expr.left)
        yield from walk(expr.right)
    elif isinstance(expr, Unary):
        yield from walk(expr.operand)
    elif isinstance(expr, FuncCall):
        for arg in expr.args:
            yield from walk(arg)


# ---------------------------------------------------------------------------
# 求值
# ---------------------------------------------------------------------------

_COMPARISON_OPS = ("=", "!=", "<>", "<", ">", "<=", ">=")


def _truthy(value) -> bool:
    """WHERE 里的真值判断：非零数字、非空串为真。"""
    return bool(value)


def _div_trunc(a: int, b: int) -> int:
    """向零取整的整数除法 —— 与 C 语言 / 408 里的一致。

    Python 的 ``//`` 是**向下取整**（-7 // 2 == -4），
    C 是向零取整（-7 / 2 == -3）。教学库对齐 C 语义，
    并用同一个函数算取模，保证 ``a = (a/b)*b + a%b`` 恒成立。
    """
    q = abs(a) // abs(b)
    return -q if (a < 0) ^ (b < 0) else q


def eval_expr(expr: Expr, env: dict[str, int], row: tuple):
    """在给定列环境与行值下求值。聚合函数在此报错（必须先被规划器消化）。"""
    if isinstance(expr, Literal):
        return expr.value

    if isinstance(expr, Column):
        # 环境的键一律小写（见 operators._env_of）；解析器产出的列名已小写，
        # 规划器生成的（如 COUNT(*)）在此统一归一，避免大小写错配。
        idx = env.get(expr.name.lower())
        if idx is None:
            raise SchemaError(f"未知列: {expr.name}")
        return row[idx]

    if isinstance(expr, FuncCall):
        raise MiniDBError(f"聚合函数 {expr.name}() 不能出现在这里（WHERE/VALUES 中不允许聚合）")

    if isinstance(expr, Unary):
        value = eval_expr(expr.operand, env, row)
        if expr.op == "NOT":
            return None if value is None else (not _truthy(value))
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeMismatchError(f"一元运算符 {expr.op} 需要数字，收到 {value!r}")
        return -value if expr.op == "-" else value

    if isinstance(expr, Binary):
        op = expr.op
        if op in ("AND", "OR"):
            left = eval_expr(expr.left, env, row)
            right = eval_expr(expr.right, env, row)
            # 三值逻辑：先把操作数归一到 {True, False, None}
            l = None if left is None else _truthy(left)
            r = None if right is None else _truthy(right)
            if op == "AND":
                if l is False or r is False:
                    return False
                if l is None or r is None:
                    return None
                return True
            if l is True or r is True:
                return True
            if l is None or r is None:
                return None
            return False

        left_val = eval_expr(expr.left, env, row)
        right_val = eval_expr(expr.right, env, row)

        if op == "IS":
            # 只与 NULL 比较（解析器保证右侧是 NULL 字面量）
            return (left_val is None) == (right_val is None)

        if op in _COMPARISON_OPS:
            if left_val is None or right_val is None:
                return None  # NULL 参与比较得 NULL，过滤时当假
            cmp = compare_values(left_val, right_val)
            if op == "=":
                return cmp == 0
            if op in ("!=", "<>"):
                return cmp != 0
            if op == "<":
                return cmp < 0
            if op == ">":
                return cmp > 0
            if op == "<=":
                return cmp <= 0
            return cmp >= 0

        # 算术运算：任一为 NULL 结果为 NULL
        if left_val is None or right_val is None:
            return None
        if isinstance(left_val, bool) or isinstance(right_val, bool) or not isinstance(
            left_val, (int, float)
        ) or not isinstance(right_val, (int, float)):
            raise TypeMismatchError(f"算术运算 {op} 需要数字，收到 {left_val!r} 与 {right_val!r}")

        if op == "+":
            return left_val + right_val
        if op == "-":
            return left_val - right_val
        if op == "*":
            return left_val * right_val
        if op == "/":
            if right_val == 0:
                raise MiniDBError("除零错误")
            if isinstance(left_val, int) and isinstance(right_val, int):
                return _div_trunc(left_val, right_val)
            return left_val / right_val
        if op == "%":
            if right_val == 0:
                raise MiniDBError("取模零错误")
            if isinstance(left_val, int) and isinstance(right_val, int):
                return left_val - _div_trunc(left_val, right_val) * right_val
            return left_val % right_val

    raise MiniDBError(f"无法求值的表达式节点: {expr!r}")


# ---------------------------------------------------------------------------
# 格式化（EXPLAIN / 输出列名）
# ---------------------------------------------------------------------------

def _prec(expr: Expr) -> int:
    if isinstance(expr, Binary):
        return _BIN_PREC.get(expr.op, _PRIMARY_PREC)
    if isinstance(expr, Unary):
        return _UNARY_PREC if expr.op == "NOT" else 7
    return _PRIMARY_PREC


def format_expr(expr: Expr) -> str:
    """把表达式打印回 SQL 文本（按优先级补括号，保证可再解析）。"""
    if isinstance(expr, Literal):
        v = expr.value
        if v is None:
            return "NULL"
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        return repr(v) if isinstance(v, float) else str(v)

    if isinstance(expr, Column):
        return expr.name

    if isinstance(expr, FuncCall):
        if expr.star:
            return f"{expr.name}(*)"
        return f"{expr.name}({', '.join(format_expr(a) for a in expr.args)})"

    if isinstance(expr, Unary):
        if expr.op == "IS" or (
            expr.op == "NOT" and isinstance(expr.operand, Binary) and expr.operand.op == "IS"
        ):
            # 特判：把 NOT(x IS NULL) 还原成 x IS NOT NULL 的读法
            target = expr.operand if expr.op == "NOT" else expr
            neg = "NOT " if expr.op == "NOT" else ""
            return f"{format_expr(target.left)} IS {neg}NULL"
        child = format_expr(expr.operand)
        if _prec(expr.operand) < _prec(expr):
            child = f"({child})"
        return f"NOT {child}" if expr.op == "NOT" else f"{expr.op}{child}"

    if isinstance(expr, Binary):
        parent = _BIN_PREC.get(expr.op, _PRIMARY_PREC)
        left = format_expr(expr.left)
        if _prec(expr.left) < parent:
            left = f"({left})"
        right = format_expr(expr.right)
        if _prec(expr.right) <= parent:  # 右结合位需要括号：a - (b - c)
            right = f"({right})"
        if expr.op == "IS":
            return f"{left} IS {right}"
        return f"{left} {expr.op} {right}"

    raise MiniDBError(f"无法格式化的表达式节点: {expr!r}")
