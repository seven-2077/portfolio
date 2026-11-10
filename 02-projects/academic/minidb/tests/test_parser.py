"""SQL 解析测试：手写 tokenizer + 递归下降 parser 的语法覆盖与错误定位。"""

from __future__ import annotations

import unittest

from minidb import parse_one, parse_script
from minidb.ast import (
    Binary,
    Column,
    CreateIndex,
    CreateTable,
    Delete,
    Explain,
    FuncCall,
    Insert,
    Literal,
    Select,
    Update,
)
from minidb.errors import SQLSyntaxError, UnterminatedStringError


class TestCreateTable(unittest.TestCase):
    def test_full_column_def(self) -> None:
        stmt = parse_one(
            "CREATE TABLE t ("
            " id INT PRIMARY KEY,"
            " name TEXT NOT NULL,"
            " score FLOAT"
            ");")
        assert isinstance(stmt, CreateTable)
        self.assertEqual(stmt.name, "t")
        kinds = [(c.name, c.col_type, c.primary_key, c.not_null)
                 for c in stmt.columns]
        self.assertEqual(kinds, [
            ("id", "INT", True, True),      # PRIMARY KEY 隐含 NOT NULL
            ("name", "TEXT", False, True),
            ("score", "FLOAT", False, False),
        ])

    def test_duplicate_column_rejected(self) -> None:
        with self.assertRaises(SQLSyntaxError):
            parse_one("CREATE TABLE t (a INT, a TEXT);")

    def test_two_primary_keys_rejected(self) -> None:
        with self.assertRaises(SQLSyntaxError):
            parse_one("CREATE TABLE t (a INT PRIMARY KEY, b INT PRIMARY KEY);")

    def test_unknown_type_rejected(self) -> None:
        with self.assertRaises(SQLSyntaxError):
            parse_one("CREATE TABLE t (a BLOB);")

    def test_create_index(self) -> None:
        stmt = parse_one("CREATE UNIQUE INDEX idx ON t (a, b);")
        assert isinstance(stmt, CreateIndex)
        self.assertEqual(
            (stmt.name, stmt.table, stmt.columns, stmt.unique),
            ("idx", "t", ["a", "b"], True))


class TestDml(unittest.TestCase):
    def test_insert_rows(self) -> None:
        stmt = parse_one("INSERT INTO t VALUES (1, 'a', 2.5), (2, 'b', NULL);")
        assert isinstance(stmt, Insert)
        self.assertEqual(stmt.table, "t")
        self.assertIsNone(stmt.columns)
        self.assertEqual(len(stmt.rows), 2)

    def test_insert_column_subset(self) -> None:
        stmt = parse_one("INSERT INTO t (a, c) VALUES (1, 3);")
        assert isinstance(stmt, Insert)
        self.assertEqual(stmt.columns, ["a", "c"])

    def test_select_full_clauses(self) -> None:
        stmt = parse_one(
            "SELECT name, score * 2 AS double FROM t"
            " WHERE score >= 80 AND dept = 'eng' OR id < 3"
            " ORDER BY score DESC, name ASC"
            " LIMIT 5 OFFSET 2;")
        assert isinstance(stmt, Select)
        self.assertEqual(stmt.table, "t")
        self.assertEqual(len(stmt.items), 2)
        self.assertEqual(stmt.items[1].alias, "double")
        assert stmt.where is not None
        self.assertEqual(stmt.where.op, "OR")       # AND 优先级更高
        self.assertEqual(stmt.where.left.op, "AND")
        self.assertEqual([o.ascending for o in stmt.order_by], [False, True])
        self.assertEqual((stmt.limit, stmt.offset), (5, 2))

    def test_select_star_and_group(self) -> None:
        stmt = parse_one(
            "SELECT dept, COUNT(*), AVG(score) FROM t"
            " WHERE score > 0 GROUP BY dept ORDER BY COUNT(*) DESC;")
        assert isinstance(stmt, Select)
        self.assertFalse(stmt.star)
        self.assertEqual(len(stmt.group_by), 1)
        aggs = [i.expr for i in stmt.items[1:]]
        assert all(isinstance(a, FuncCall) for a in aggs)
        self.assertTrue(aggs[0].star)              # COUNT(*)
        # ORDER BY 里的聚合也进了 order_by
        self.assertIsInstance(stmt.order_by[0].expr, FuncCall)

    def test_select_star(self) -> None:
        stmt = parse_one("SELECT * FROM t;")
        assert isinstance(stmt, Select)
        self.assertTrue(stmt.star)

    def test_update_delete(self) -> None:
        upd = parse_one("UPDATE t SET a = a + 1, b = 'x' WHERE id = 3;")
        assert isinstance(upd, Update)
        self.assertEqual([c for c, _e in upd.assignments], ["a", "b"])
        self.assertEqual(upd.where.op, "=")

        dele = parse_one("DELETE FROM t WHERE id = 3;")
        assert isinstance(dele, Delete)
        self.assertEqual(dele.table, "t")

    def test_delete_without_where(self) -> None:
        stmt = parse_one("DELETE FROM t;")
        assert isinstance(stmt, Delete)
        self.assertIsNone(stmt.where)

    def test_explain_wraps_statement(self) -> None:
        stmt = parse_one("EXPLAIN SELECT * FROM t WHERE id = 1;")
        assert isinstance(stmt, Explain)
        self.assertIsInstance(stmt.stmt, Select)

    def test_explain_of_ddl(self) -> None:
        stmt = parse_one("EXPLAIN CREATE TABLE t (a INT);")
        assert isinstance(stmt, Explain)
        self.assertIsInstance(stmt.stmt, CreateTable)


class TestScript(unittest.TestCase):
    def test_multi_statement(self) -> None:
        stmts = parse_script(
            "CREATE TABLE t (a INT); INSERT INTO t VALUES (1); SELECT * FROM t;")
        self.assertEqual(len(stmts), 3)
        self.assertIsInstance(stmts[0], CreateTable)
        self.assertIsInstance(stmts[1], Insert)
        self.assertIsInstance(stmts[2], Select)

    def test_trailing_and_extra_semicolons(self) -> None:
        stmts = parse_script(";; SELECT * FROM t ; ;")
        self.assertEqual(len(stmts), 1)

    def test_missing_semicolon_between_statements(self) -> None:
        with self.assertRaises(SQLSyntaxError):
            parse_script("SELECT * FROM t SELECT * FROM t")


class TestErrors(unittest.TestCase):
    def test_error_carries_position(self) -> None:
        with self.assertRaises(SQLSyntaxError) as ctx:
            parse_one("SELECT\nFROM t;")
        self.assertEqual(ctx.exception.line, 2)     # 错误在第 2 行
        self.assertGreater(ctx.exception.col, 0)

    def test_unterminated_string(self) -> None:
        with self.assertRaises(UnterminatedStringError):
            parse_one("SELECT * FROM t WHERE name = 'abc;")

    def test_garbage_input(self) -> None:
        with self.assertRaises(SQLSyntaxError):
            parse_one("FROM SELECT WHERE;")


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
