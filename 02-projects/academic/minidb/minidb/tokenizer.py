r"""手写词法分析器（tokenizer）—— 不用正则，逐字符扫描。

为什么坚持手写？正则 ``re.match(r"\d+")`` 之类看起来省事，但：
1) 位置信息（行/列）要另算一遍；2) 字符串里的 ``''`` 转义、
   ``--`` 注释、``1e-3`` 指数这些状态机逻辑用正则会碎成好几段；
   3) 教学项目要让人**一眼看清 token 是怎么产生的**。

产出的 Token 流带 kind / value / 行列号，交给递归下降解析器 ——
这正是编译原理课「词法分析 -> 语法分析」的标准两段式。

Token 类型：
* KEYWORD  保留字（大写规范化，如 SELECT）
* IDENT    标识符（保留原始大小写，引用处再小写化）
* NUMBER   数字（Python int / float，指数或小数点即 FLOAT）
* STRING   单引号字符串（``''`` 转义一个单引号）
* OP       运算符与标点
* EOF      输入结束哨兵
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SQLSyntaxError, UnterminatedStringError

# 保留字。类型名（INT/TEXT/FLOAT）与聚合函数名（COUNT/SUM...）**不是**关键字，
# 它们以 IDENT 形式出现、由解析器按上下文解释 —— 这样列名叫 count / text 也合法。
KEYWORDS = frozenset(
    {
        "CREATE", "TABLE", "INDEX", "UNIQUE", "PRIMARY", "KEY", "NOT", "NULL",
        "INSERT", "INTO", "VALUES", "SELECT", "FROM", "WHERE", "AND", "OR",
        "GROUP", "BY", "ORDER", "ASC", "DESC", "LIMIT", "OFFSET", "IS",
        "DELETE", "UPDATE", "SET", "EXPLAIN", "AS", "ON",
    }
)

_TWO_CHAR_OPS = ("<>", "!=", "<=", ">=")
_ONE_CHAR_OPS = frozenset("=<>+-*/%(),;")


@dataclass(frozen=True)
class Token:
    kind: str
    value: object  # KEYWORD/OP 为 str，NUMBER 为 int/float，STRING 为 str
    line: int
    col: int


def tokenize(sql: str) -> list[Token]:
    """把 SQL 文本切成 Token 流（含末尾 EOF）。词法错误抛 SQLSyntaxError。"""
    tokens: list[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(sql)

    while i < n:
        ch = sql[i]

        # -- 空白与换行 ----------------------------------------------------
        if ch == "\n":
            i += 1
            line += 1
            col = 1
            continue
        if ch in " \t\r":
            i += 1
            col += 1
            continue

        # -- 行注释 -- ... --------------------------------------------------
        if ch == "-" and sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                i += 1
                col += 1
            continue

        # -- 字符串字面量（支持 '' 转义，可跨行）---------------------------
        if ch == "'":
            start_line, start_col = line, col
            i += 1
            col += 1
            buf: list[str] = []
            closed = False
            while i < n:
                c = sql[i]
                if c == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        buf.append("'")
                        i += 2
                        col += 2
                        continue
                    i += 1
                    col += 1
                    closed = True
                    break
                if c == "\n":
                    buf.append(c)
                    i += 1
                    line += 1
                    col = 1
                    continue
                buf.append(c)
                i += 1
                col += 1
            if not closed:
                raise UnterminatedStringError("字符串字面量未闭合（缺少 '）", start_line, start_col)
            tokens.append(Token("STRING", "".join(buf), start_line, start_col))
            continue

        # -- 数字（整数 / 小数 / 指数）------------------------------------
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            start_line, start_col = line, col
            j = i
            while j < n and sql[j].isdigit():
                j += 1
            is_float = False
            if j < n and sql[j] == ".":
                is_float = True
                j += 1
                while j < n and sql[j].isdigit():
                    j += 1
            if j < n and sql[j] in "eE":
                k = j + 1
                if k < n and sql[k] in "+-":
                    k += 1
                if k < n and sql[k].isdigit():
                    is_float = True
                    j = k
                    while j < n and sql[j].isdigit():
                        j += 1
            text = sql[i:j]
            tokens.append(Token("NUMBER", float(text) if is_float else int(text), start_line, start_col))
            col += j - i
            i = j
            continue

        # -- 标识符 / 关键字 ------------------------------------------------
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            text = sql[i:j]
            if text.upper() in KEYWORDS:
                tokens.append(Token("KEYWORD", text.upper(), line, col))
            else:
                tokens.append(Token("IDENT", text, line, col))
            col += j - i
            i = j
            continue

        # -- 运算符与标点 --------------------------------------------------
        two = sql[i : i + 2]
        if two in _TWO_CHAR_OPS:
            tokens.append(Token("OP", two, line, col))
            i += 2
            col += 2
            continue
        if ch in _ONE_CHAR_OPS:
            tokens.append(Token("OP", ch, line, col))
            i += 1
            col += 1
            continue

        raise SQLSyntaxError(f"无法识别的字符: {ch!r}", line, col)

    tokens.append(Token("EOF", "", line, col))
    return tokens


def is_complete(sql: str) -> bool:
    """REPL 用：这段输入是否是一条完整语句？

    完整 = 词法上闭合（字符串没断）**且**最后一个 token 是 ``;``。
    字符串未闭合抛 UnterminatedStringError，由调用方继续读入下一行。
    """
    tokens = tokenize(sql)  # 未闭合字符串会抛 UnterminatedStringError
    body = [t for t in tokens if t.kind != "EOF"]
    return bool(body) and body[-1].kind == "OP" and body[-1].value == ";"
