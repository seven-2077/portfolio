"""递归下降语法分析器 —— 手写 tokenizer 之上的第二层。

文法（EBNF，代码结构与之一一对应，读代码即读文法）::

    statement   := create_table | create_index | insert | select
                 | delete | update | explain
    create_table:= CREATE TABLE ident '(' column_def (',' column_def)* ')'
    column_def  := ident type_name (PRIMARY KEY | NOT NULL)*
    create_index:= CREATE [UNIQUE] INDEX ident ON ident '(' ident_list ')'
    insert      := INSERT INTO ident [ '(' ident_list ')' ]
                   VALUES '(' expr_list ')' (',' '(' expr_list ')')*
    select      := SELECT select_list FROM ident [WHERE expr]
                   [GROUP BY expr_list] [ORDER BY order_item*]
                   [LIMIT n] [OFFSET n]
    delete      := DELETE FROM ident [WHERE expr]
    update      := UPDATE ident SET assign (',' assign)* [WHERE expr]
    explain     := EXPLAIN statement

    expr        := or_expr
    or_expr     := and_expr (OR and_expr)*
    and_expr    := not_expr (AND not_expr)*
    not_expr    := NOT not_expr | comparison
    comparison  := additive (('='|'!='|'<>'|'<'|'<='|'>'|'>=') additive
                   | IS [NOT] NULL)?
    additive    := multiplicative (('+'|'-') multiplicative)*
    multiplicative := unary (('*'|'/'|'%') unary)*
    unary       := ('-'|'+') unary | primary
    primary     := NUMBER | STRING | NULL | '(' expr ')'
                 | ident '(' [expr_list | '*'] ')' | ident

为什么不用 parser generator？
教学项目要展示的就是「每个非终结符一个函数、每个产生式一段代码」的
直译美感 —— 这正是龙书里 LL(1) 递归下降的标准写法；
而且错误信息能精确到行列、能说出「期望什么」。

一个刻意的简化：表达式**不支持链式比较**（``a < b < c`` 直接语法错误），
这与 Python 不同、与 SQL 标准一致。
"""

from __future__ import annotations

from typing import Optional

from .ast import (
    Binary,
    Column,
    ColumnDef,
    CreateIndex,
    CreateTable,
    Delete,
    Expr,
    Explain,
    FuncCall,
    Insert,
    Literal,
    OrderItem,
    Select,
    SelectItem,
    Statement,
    Unary,
    Update,
)
from .codec import normalize_type
from .errors import SQLSyntaxError
from .tokenizer import Token, tokenize

# 允许写在列定义里的类型名（含别名）
_TYPE_NAMES = {"INT", "INTEGER", "TEXT", "FLOAT", "REAL"}
_COMPARISON_OPS = ("=", "!=", "<>", "<", "<=", ">", ">=")


class Parser:
    """Token 流上的递归下降解析器。"""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # -- 游标工具 -----------------------------------------------------------

    def peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def at_end(self) -> bool:
        return self.peek().kind == "EOF"

    def check_keyword(self, *names: str) -> bool:
        tok = self.peek()
        return tok.kind == "KEYWORD" and tok.value in names

    def expect_keyword(self, name: str) -> Token:
        if not self.check_keyword(name):
            self.error(f"期望关键字 {name}")
        return self.advance()

    def check_op(self, *ops: str) -> bool:
        tok = self.peek()
        return tok.kind == "OP" and tok.value in ops

    def expect_op(self, op: str) -> Token:
        if not self.check_op(op):
            self.error(f"期望符号 {op}")
        return self.advance()

    def expect_ident(self, what: str = "标识符") -> Token:
        tok = self.peek()
        if tok.kind != "IDENT":
            self.error(f"期望{what}")
        return self.advance()

    def error(self, message: str) -> None:
        tok = self.peek()
        found = "输入结束" if tok.kind == "EOF" else repr(tok.value)
        raise SQLSyntaxError(f"{message}，但遇到 {found}", tok.line, tok.col)

    # -- 语句分发 -----------------------------------------------------------

    def parse_statement(self) -> Statement:
        if self.check_keyword("CREATE"):
            return self.parse_create()
        if self.check_keyword("INSERT"):
            return self.parse_insert()
        if self.check_keyword("SELECT"):
            return self.parse_select()
        if self.check_keyword("DELETE"):
            return self.parse_delete()
        if self.check_keyword("UPDATE"):
            return self.parse_update()
        if self.check_keyword("EXPLAIN"):
            self.advance()
            return Explain(self.parse_statement())
        self.error("期望语句（CREATE / INSERT / SELECT / DELETE / UPDATE / EXPLAIN）")
        raise AssertionError("unreachable")

    def parse_create(self) -> Statement:
        self.expect_keyword("CREATE")
        if self.check_keyword("TABLE"):
            return self.parse_create_table()
        if self.check_keyword("UNIQUE") or self.check_keyword("INDEX"):
            return self.parse_create_index()
        self.error("期望 TABLE 或 INDEX")
        raise AssertionError("unreachable")

    def parse_create_table(self) -> CreateTable:
        self.expect_keyword("TABLE")
        name = self.expect_ident("表名").value  # 保留原始大小写
        self.expect_op("(")
        columns: list[ColumnDef] = []
        seen: set[str] = set()
        while True:
            col_name = self.expect_ident("列名").value
            if col_name.lower() in seen:
                raise SQLSyntaxError(f"列名重复: {col_name}", self.peek().line, self.peek().col)
            seen.add(col_name.lower())
            type_tok = self.expect_ident("类型名（INT / TEXT / FLOAT）")
            raw_type = str(type_tok.value).upper()
            if raw_type not in _TYPE_NAMES:
                raise SQLSyntaxError(
                    f"不支持的列类型: {type_tok.value}（支持 INT / TEXT / FLOAT）",
                    type_tok.line, type_tok.col,
                )
            # 可选的长度修饰：VARCHAR(255) / CHAR(10) —— 只接受不执行，
            # 教学库是变长存储，长度参数是声明习惯而非存储约束
            if self.check_op("("):
                self.advance()
                if not (self.peek().kind == "NUMBER"
                        and isinstance(self.peek().value, int)):
                    self.error("类型长度必须是整数")
                self.advance()
                self.expect_op(")")
            primary_key = False
            not_null = False
            while self.check_keyword("PRIMARY", "NOT"):
                if self.check_keyword("PRIMARY"):
                    self.advance()
                    self.expect_keyword("KEY")
                    primary_key = True
                else:
                    self.advance()
                    self.expect_keyword("NULL")
                    not_null = True
            if primary_key:
                not_null = True  # 主键隐含 NOT NULL（SQL 标准）
            columns.append(ColumnDef(col_name, normalize_type(raw_type), primary_key, not_null))
            if self.check_op(","):
                self.advance()
                continue
            break
        self.expect_op(")")
        if not columns:
            raise SQLSyntaxError("CREATE TABLE 至少需要一列", self.peek().line, self.peek().col)
        if sum(1 for c in columns if c.primary_key) > 1:
            raise SQLSyntaxError("暂不支持复合主键（只允许一个 PRIMARY KEY）",
                                 self.peek().line, self.peek().col)
        return CreateTable(name, columns)

    def parse_create_index(self) -> CreateIndex:
        unique = False
        if self.check_keyword("UNIQUE"):
            self.advance()
            unique = True
        self.expect_keyword("INDEX")
        name = self.expect_ident("索引名").value
        self.expect_keyword("ON")
        table = self.expect_ident("表名").value.lower()
        self.expect_op("(")
        columns = [self.expect_ident("列名").value]
        while self.check_op(","):
            self.advance()
            columns.append(self.expect_ident("列名").value)
        self.expect_op(")")
        return CreateIndex(name, table, columns, unique)

    def parse_insert(self) -> Insert:
        self.expect_keyword("INSERT")
        self.expect_keyword("INTO")
        table = self.expect_ident("表名").value.lower()
        columns: Optional[list[str]] = None
        if self.check_op("("):
            self.advance()
            columns = [self.expect_ident("列名").value.lower()]
            while self.check_op(","):
                self.advance()
                columns.append(self.expect_ident("列名").value.lower())
            self.expect_op(")")
        self.expect_keyword("VALUES")
        rows: list[list[Expr]] = []
        while True:
            self.expect_op("(")
            values = [self.parse_expr()]
            while self.check_op(","):
                self.advance()
                values.append(self.parse_expr())
            self.expect_op(")")
            rows.append(values)
            if self.check_op(","):
                self.advance()
                continue
            break
        return Insert(table, columns, rows)

    def parse_select(self) -> Select:
        self.expect_keyword("SELECT")
        items: list[SelectItem] = []
        star = False
        if self.check_op("*"):
            self.advance()
            star = True
        else:
            while True:
                expr = self.parse_expr()
                alias = None
                if self.check_keyword("AS"):
                    self.advance()
                    alias = self.expect_ident("别名").value
                items.append(SelectItem(expr, alias))
                if self.check_op(","):
                    self.advance()
                    continue
                break
        self.expect_keyword("FROM")
        table = self.expect_ident("表名").value.lower()

        where: Optional[Expr] = None
        if self.check_keyword("WHERE"):
            self.advance()
            where = self.parse_expr()

        group_by: list[Expr] = []
        if self.check_keyword("GROUP"):
            self.advance()
            self.expect_keyword("BY")
            group_by.append(self.parse_expr())
            while self.check_op(","):
                self.advance()
                group_by.append(self.parse_expr())

        order_by: list[OrderItem] = []
        if self.check_keyword("ORDER"):
            self.advance()
            self.expect_keyword("BY")
            while True:
                expr = self.parse_expr()
                ascending = True
                if self.check_keyword("ASC", "DESC"):
                    ascending = self.advance().value == "ASC"
                order_by.append(OrderItem(expr, ascending))
                if self.check_op(","):
                    self.advance()
                    continue
                break

        limit: Optional[int] = None
        offset = 0
        if self.check_keyword("LIMIT"):
            self.advance()
            limit = self._parse_nonneg_int("LIMIT")
        if self.check_keyword("OFFSET"):
            self.advance()
            offset = self._parse_nonneg_int("OFFSET")

        return Select(table, items, star, where, group_by, order_by, limit, offset)

    def _parse_nonneg_int(self, clause: str) -> int:
        tok = self.peek()
        if tok.kind != "NUMBER" or not isinstance(tok.value, int) or tok.value < 0:
            raise SQLSyntaxError(f"{clause} 需要非负整数", tok.line, tok.col)
        self.advance()
        return tok.value

    def parse_delete(self) -> Delete:
        self.expect_keyword("DELETE")
        self.expect_keyword("FROM")
        table = self.expect_ident("表名").value.lower()
        where = None
        if self.check_keyword("WHERE"):
            self.advance()
            where = self.parse_expr()
        return Delete(table, where)

    def parse_update(self) -> Update:
        self.expect_keyword("UPDATE")
        table = self.expect_ident("表名").value.lower()
        self.expect_keyword("SET")
        assignments: list[tuple[str, Expr]] = []
        while True:
            col = self.expect_ident("列名").value.lower()
            self.expect_op("=")
            assignments.append((col, self.parse_expr()))
            if self.check_op(","):
                self.advance()
                continue
            break
        where = None
        if self.check_keyword("WHERE"):
            self.advance()
            where = self.parse_expr()
        return Update(table, assignments, where)

    # -- 表达式（优先级爬升）------------------------------------------------

    def parse_expr(self) -> Expr:
        return self.parse_or()

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.check_keyword("OR"):
            self.advance()
            left = Binary("OR", left, self.parse_and())
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self.check_keyword("AND"):
            self.advance()
            left = Binary("AND", left, self.parse_not())
        return left

    def parse_not(self) -> Expr:
        # NOT 的优先级低于比较、高于 AND：NOT a = b 解析成 NOT (a = b)
        if self.check_keyword("NOT"):
            self.advance()
            return Unary("NOT", self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        left = self.parse_additive()
        if self.check_op(*_COMPARISON_OPS):
            op = str(self.advance().value)
            return Binary(str(op), left, self.parse_additive())
        if self.check_keyword("IS"):
            self.advance()
            if self.check_keyword("NOT"):
                self.advance()
                self.expect_keyword("NULL")
                return Unary("NOT", Binary("IS", left, Literal(None)))
            self.expect_keyword("NULL")
            return Binary("IS", left, Literal(None))
        return left

    def parse_additive(self) -> Expr:
        left = self.parse_multiplicative()
        while self.check_op("+", "-"):
            op = str(self.advance().value)
            left = Binary(op, left, self.parse_multiplicative())
        return left

    def parse_multiplicative(self) -> Expr:
        left = self.parse_unary()
        while self.check_op("*", "/", "%"):
            op = str(self.advance().value)
            left = Binary(op, left, self.parse_unary())
        return left

    def parse_unary(self) -> Expr:
        if self.check_op("-", "+"):
            op = str(self.advance().value)
            return Unary(op, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        tok = self.peek()
        if tok.kind == "NUMBER":
            self.advance()
            return Literal(tok.value)
        if tok.kind == "STRING":
            self.advance()
            return Literal(tok.value)
        if self.check_keyword("NULL"):
            self.advance()
            return Literal(None)
        if self.check_op("("):
            self.advance()
            inner = self.parse_expr()
            self.expect_op(")")
            return inner
        if tok.kind == "IDENT":
            name = str(tok.value)
            if self.peek(1).kind == "OP" and self.peek(1).value == "(":
                # 函数调用：聚合函数名不是关键字，靠「标识符后跟 (」识别
                self.advance()
                self.advance()
                if self.check_op("*"):
                    self.advance()
                    self.expect_op(")")
                    return FuncCall(name.upper(), [], star=True)
                args: list[Expr] = []
                if not self.check_op(")"):
                    args.append(self.parse_expr())
                    while self.check_op(","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect_op(")")
                return FuncCall(name.upper(), args)
            self.advance()
            return Column(name.lower())  # 引用统一小写，免去大小写匹配问题
        self.error("期望表达式")
        raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# 模块级入口
# ---------------------------------------------------------------------------

def parse_script(sql: str) -> list[Statement]:
    """解析一段可含多条 ``;`` 分隔语句的脚本（先全部解析成功才返回）。"""
    parser = Parser(tokenize(sql))
    statements: list[Statement] = []
    while not parser.at_end():
        if parser.check_op(";"):
            parser.advance()
            continue
        statements.append(parser.parse_statement())
        if parser.check_op(";"):
            parser.advance()
        elif not parser.at_end():
            parser.error("语句之间缺少 ;")
    return statements


def parse_one(sql: str) -> Statement:
    """解析单条语句（测试用）。"""
    statements = parse_script(sql)
    if len(statements) != 1:
        raise SQLSyntaxError(f"期望恰好 1 条语句，实际 {len(statements)} 条")
    return statements[0]
