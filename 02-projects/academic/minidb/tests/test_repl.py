"""REPL 测试：分号缓冲、元命令、错误恢复、表格渲染（注入 StringIO）。"""

from __future__ import annotations

from io import StringIO

from support import SEED_SQL, TempDbCase

from minidb.repl import Repl, format_table


def run_repl(db, script: str) -> str:
    """把 script 喂给 REPL，返回全部 stdout 文本。"""
    out = StringIO()
    repl = Repl(db, stdin=StringIO(script), stdout=out)
    repl.run()
    return out.getvalue()


class TestRepl(TempDbCase):
    def test_banner_and_quit(self) -> None:
        out = run_repl(self.db, ".quit\n")
        self.assertIn("minidb", out)

    def test_eof_also_exits(self) -> None:
        out = run_repl(self.db, "")          # 直接 EOF 也应优雅退出
        self.assertIn("minidb", out)

    def test_meta_tables_and_schema(self) -> None:
        self.db.executescript(SEED_SQL)
        self.db.execute("CREATE INDEX idx_dept ON student (dept);")
        out = run_repl(self.db, ".tables\n.indexes\n.schema\n.quit\n")
        self.assertIn("student", out)
        self.assertIn("idx_dept", out)
        self.assertIn("CREATE TABLE student", out)
        self.assertIn("CREATE INDEX idx_dept", out)

    def test_schema_single_table(self) -> None:
        self.db.executescript(SEED_SQL)
        self.db.execute("CREATE TABLE other (x INT);")
        out = run_repl(self.db, ".schema student\n.quit\n")
        self.assertIn("CREATE TABLE student", out)
        self.assertNotIn("CREATE TABLE other", out)

    def test_multi_statement_single_line(self) -> None:
        out = run_repl(
            self.db,
            "CREATE TABLE t (id INT PRIMARY KEY);"
            "INSERT INTO t VALUES (1);"
            "INSERT INTO t VALUES (2);\n"
            "SELECT * FROM t;\n.quit\n")
        self.assertIn("插入 1 行", out)
        self.assertIn("(2 行)", out)

    def test_multiline_statement_buffering(self) -> None:
        self.db.executescript(SEED_SQL)
        out = run_repl(
            self.db,
            "SELECT name FROM student\n"      # 没有 ; -> 续行
            "WHERE id = 1;\n.quit\n")
        self.assertIn("Alice", out)

    def test_error_does_not_kill_session(self) -> None:
        out = run_repl(
            self.db,
            "SELECT * FROM ghost;\n"                  # 报错
            "CREATE TABLE t (id INT PRIMARY KEY);\n"   # 会话继续
            "INSERT INTO t VALUES (1);\n.quit\n")
        self.assertIn("错误:", out)
        self.assertIn("已创建表 t", out)
        self.assertIn("插入 1 行", out)

    def test_unknown_meta_command(self) -> None:
        out = run_repl(self.db, ".frobnicate\n.quit\n")
        self.assertIn("未知元命令", out)

    def test_help_lists_commands(self) -> None:
        out = run_repl(self.db, ".help\n.quit\n")
        for cmd in (".tables", ".schema", ".crash", ".quit"):
            self.assertIn(cmd, out)

    def test_crash_failpoint_injection(self) -> None:
        # .crash 注入后下一次提交「崩溃」；REPL 不应被 SimulatedCrash 打死
        out = run_repl(
            self.db,
            "CREATE TABLE t (id INT PRIMARY KEY);\n"
            ".crash before_commit\n"
            "INSERT INTO t VALUES (1);\n"
            ".quit\n")
        self.assertIn("已注入故障点 before_commit", out)
        self.assertIn("SimulatedCrash", out)   # 被兜底捕获，会话不中断


class TestFormatTable(TempDbCase):
    def test_alignment_and_null(self) -> None:
        text = format_table(
            ["id", "name", "score"],
            [(1, "Alice", 92.5), (20, None, 7.0)])
        lines = text.splitlines()
        # 表头 + 分隔线 + 2 行数据 + 收尾线
        self.assertTrue(lines[0].startswith("+"))
        self.assertIn("id", lines[1])
        self.assertIn("NULL", text)
        # 单元格按 | 切开核对：数值列右对齐，92.5 / 7.0 占满列宽
        row1 = lines[3].split("|")
        row2 = lines[4].split("|")
        self.assertEqual(row1[1].strip(), "1")
        self.assertEqual(row1[3].strip(), "92.5")
        self.assertEqual(row2[1].strip(), "20")
        self.assertEqual(row2[2].strip(), "NULL")
        self.assertEqual(row2[3].strip(), "7.0")
        self.assertIn("(2 行)", text)

    def test_empty_result(self) -> None:
        text = format_table(["id"], [])
        self.assertIn("(0 行)", text)


if __name__ == "__main__":      # pragma: no cover
    import unittest
    unittest.main()
