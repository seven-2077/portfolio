"""执行器端到端测试：SQL -> 计划 -> Volcano 算子 -> 结果。

覆盖：投影/过滤/排序/分页、聚合与 GROUP BY、索引存取路径（EXPLAIN）、
约束与错误回滚、二级索引与 UNIQUE、NULL 语义。
"""

from __future__ import annotations

from support import SEED_SQL, TempDbCase

from minidb.errors import (
    DuplicateKeyError,
    NotNullError,
    SchemaError,
    TypeMismatchError,
)


class TestSelect(TempDbCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_select_star_order(self) -> None:
        rows = self.db.query("SELECT * FROM student;")
        self.assertEqual(len(rows), 10)
        # 堆按 rowid 顺序扫，插入序即输出序
        self.assertEqual([r[0] for r in rows], list(range(1, 11)))

    def test_projection_alias_expression(self) -> None:
        rows = self.db.query(
            "SELECT name, score * 2 AS double FROM student WHERE id = 1;")
        self.assertEqual(rows, [("Alice", 185.0)])

    def test_where_comparisons(self) -> None:
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE score >= 90;"),
            [1, 3, 7, 10])
        # score < 80: Dan(71) Frank(79.5) Heidi(64)，且都 != 5
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE id <> 5 AND score < 80;"),
            [4, 6, 8])
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE name = 'Bob';"), [2])

    def test_where_and_or(self) -> None:
        # AND 优先级高于 OR：a AND b OR c == (a AND b) OR c
        # eng&>90: Alice(92.5) Carol(95.5)；ops&<80: Dan(71)
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE dept = 'eng' AND score > 90"
                     " OR dept = 'ops' AND score < 80;"),
            [1, 3, 4])
        # score < 75: Dan(71) Heidi(64)；dept='hr': Bob Frank Ivan
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE score < 75 OR dept = 'hr';"),
            [2, 4, 6, 8, 9])

    def test_where_is_null(self) -> None:
        self.db.execute("INSERT INTO student (id, name) VALUES (11, 'Mallory');")
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE score IS NULL;"), [11])
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE score IS NOT NULL"
                     " AND id > 9;"),
            [10])

    def test_order_limit_offset(self) -> None:
        self.assertEqual(
            self.ids("SELECT id FROM student ORDER BY score DESC LIMIT 3;"),
            [10, 3, 1])
        self.assertEqual(
            self.ids("SELECT id FROM student ORDER BY id DESC"
                     " LIMIT 3 OFFSET 2;"),
            [8, 7, 6])
        # 多键排序：先按 dept，再按 score 升序
        rows = self.db.query(
            "SELECT id FROM student WHERE dept = 'hr'"
            " ORDER BY dept, score;")
        self.assertEqual([r[0] for r in rows], [6, 9, 2])   # 79.5 < 83.5 < 87


class TestAggregate(TempDbCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_bare_aggregates(self) -> None:
        row = self.db.query(
            "SELECT COUNT(*), SUM(score), AVG(score),"
            " MIN(score), MAX(score) FROM student;")[0]
        count, total, avg, lo, hi = row
        self.assertEqual(count, 10)
        self.assertAlmostEqual(total, 848.0)
        self.assertAlmostEqual(avg, 84.8)
        self.assertEqual((lo, hi), (64.0, 96.0))

    def test_count_column_ignores_null(self) -> None:
        self.db.execute(
            "INSERT INTO student (id, name) VALUES (11, 'NoScore');")
        row = self.db.query(
            "SELECT COUNT(*), COUNT(score) FROM student;")[0]
        self.assertEqual(row, (11, 10))       # COUNT(col) 跳过 NULL

    def test_group_by(self) -> None:
        rows = self.db.query(
            "SELECT dept, COUNT(*), AVG(score) FROM student"
            " GROUP BY dept ORDER BY dept;")
        self.assertEqual(len(rows), 3)
        self.assertEqual([r[:2] for r in rows],
                         [("eng", 4), ("hr", 3), ("ops", 3)])
        # 用与实现同序的浮点求和核对均值（hr: 87+79.5+83.5 = 250）
        self.assertEqual(rows[0][2], (92.5 + 95.5 + 88.0 + 64.0) / 4)
        self.assertEqual(rows[1][2], (87.0 + 79.5 + 83.5) / 3)
        self.assertEqual(rows[2][2], (71.0 + 91.0 + 96.0) / 3)

    def test_group_by_order_by_aggregate(self) -> None:
        rows = self.db.query(
            "SELECT dept FROM student GROUP BY dept"
            " ORDER BY COUNT(*) DESC, dept;")
        # eng=4 最多；hr、ops 都是 3，按 dept 升序
        self.assertEqual([r[0] for r in rows], ["eng", "hr", "ops"])

    def test_empty_table_aggregate(self) -> None:
        self.db.execute("CREATE TABLE empty (a INT);")
        row = self.db.query("SELECT COUNT(*), AVG(a) FROM empty;")[0]
        self.assertEqual(row, (0, None))      # SQL 标准：空表也出一行


class TestDml(TempDbCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_update_where(self) -> None:
        result = self.db.execute(
            "UPDATE student SET score = score + 1 WHERE dept = 'ops';")
        self.assertEqual(result.rowcount, 3)
        self.assertEqual(
            self.db.query("SELECT score FROM student WHERE id = 4;"),
            [(72.0,)])

    def test_update_primary_key_syncs_index(self) -> None:
        self.db.execute("UPDATE student SET id = 100 WHERE id = 1;")
        self.assertEqual(
            self.db.query("SELECT name FROM student WHERE id = 100;"),
            [("Alice",)])
        # 旧键必须从主键索引里消失（否则 IndexScan 会读到幻影行）
        self.assertEqual(
            self.db.query("SELECT name FROM student WHERE id = 1;"), [])

    def test_delete_where(self) -> None:
        result = self.db.execute("DELETE FROM student WHERE dept = 'hr';")
        self.assertEqual(result.rowcount, 3)
        self.assertEqual(len(self.db.query("SELECT * FROM student;")), 7)
        # 索引条目同步摘除
        self.assertEqual(
            self.db.query("SELECT name FROM student WHERE id = 2;"), [])

    def test_insert_subset_columns(self) -> None:
        self.db.execute(
            "INSERT INTO student (id, name) VALUES (11, 'Mallory');")
        row = self.db.query("SELECT * FROM student WHERE id = 11;")[0]
        self.assertEqual(row, (11, "Mallory", None, None))


class TestErrorsAndRollback(TempDbCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_duplicate_primary_key(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.execute(
                "INSERT INTO student VALUES (1, 'X', 'eng', 60.0);")
        self.assertEqual(len(self.db.query("SELECT * FROM student;")), 10)

    def test_not_null_violation(self) -> None:
        with self.assertRaises(NotNullError):
            self.db.execute(
                "INSERT INTO student (id, name) VALUES (11, NULL);")

    def test_type_mismatch(self) -> None:
        with self.assertRaises(TypeMismatchError):
            self.db.execute(
                "INSERT INTO student VALUES (11, 'X', 'eng', 'abc');")

    def test_unknown_table_and_column(self) -> None:
        with self.assertRaises(SchemaError):
            self.db.query("SELECT * FROM ghost;")
        with self.assertRaises(SchemaError):
            self.db.query("SELECT ghost_col FROM student;")

    def test_multi_row_insert_rolls_back_whole_statement(self) -> None:
        # 第二行主键撞车 -> 整条语句回滚，第一行也不能落地
        with self.assertRaises(DuplicateKeyError):
            self.db.execute(
                "INSERT INTO student VALUES"
                " (100, 'X', 'eng', 60.0),"
                " (1, 'Y', 'eng', 60.0);")
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE id >= 100;"), [])

    def test_failed_statement_survives_reopen(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.execute(
                "INSERT INTO student VALUES (1, 'X', 'eng', 60.0);")
        self.reopen()
        self.assertEqual(len(self.db.query("SELECT * FROM student;")), 10)


class TestExplainAndIndexes(TempDbCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_full_scan_plan(self) -> None:
        plan = self.db.execute("EXPLAIN SELECT * FROM student;").plan_text
        self.assertIn("SeqScan", plan)
        self.assertIn("Project", plan)

    def test_primary_key_lookup_uses_index(self) -> None:
        plan = self.db.execute(
            "EXPLAIN SELECT name FROM student WHERE id = 2;").plan_text
        self.assertIn("IndexScan", plan)
        self.assertIn("student_pk", plan)
        # 索引已消费该合取项，不必再套 Filter
        self.assertNotIn("Filter", plan)
        # 计划正确性：结果与全表扫一致
        self.assertEqual(
            self.db.query("SELECT name FROM student WHERE id = 2;"),
            [("Bob",)])

    def test_order_by_pk_skips_sort(self) -> None:
        plan = self.db.execute(
            "EXPLAIN SELECT id FROM student ORDER BY id;").plan_text
        self.assertIn("IndexScan", plan)
        self.assertNotIn("Sort", plan)

    def test_secondary_index_scan(self) -> None:
        self.db.execute("CREATE INDEX idx_dept ON student (dept);")
        plan = self.db.execute(
            "EXPLAIN SELECT id FROM student WHERE dept = 'eng';").plan_text
        self.assertIn("IndexScan", plan)
        self.assertIn("idx_dept", plan)
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE dept = 'eng';"),
            [1, 3, 5, 8])

    def test_secondary_index_allows_duplicate_values(self) -> None:
        # 非唯一索引：dept 本来就有重复值，建索引必须成功
        # （键尾部拼了主键，条目依然全树唯一）
        result = self.db.execute("CREATE INDEX idx_dept ON student (dept);")
        self.assertEqual(result.kind, "ddl")
        _, indexes = self.db.catalog_names()
        self.assertEqual(indexes, ["idx_dept"])

    def test_unique_index_rejects_existing_duplicates(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.execute("CREATE UNIQUE INDEX idx_dept ON student (dept);")
        # 整条 DDL 回滚：索引不能留下半截
        _, indexes = self.db.catalog_names()
        self.assertEqual(indexes, [])

    def test_unique_index_enforced_on_insert(self) -> None:
        self.db.execute(
            "CREATE TABLE users (id INT PRIMARY KEY, email TEXT);")
        self.db.execute(
            "INSERT INTO users VALUES (1, 'a@x.com'), (2, 'b@x.com');")
        self.db.execute("CREATE UNIQUE INDEX idx_email ON users (email);")
        with self.assertRaises(DuplicateKeyError):
            self.db.execute(
                "INSERT INTO users VALUES (3, 'a@x.com');")
        # 合法插入不受影响
        self.db.execute(
            "INSERT INTO users VALUES (4, 'c@x.com');")
        self.assertEqual(len(self.db.query("SELECT * FROM users;")), 3)

    def test_update_through_indexed_predicate(self) -> None:
        # UpdateOp 先物化再改：边扫边改索引不会漏行/重复行
        self.db.execute("CREATE INDEX idx_dept ON student (dept);")
        result = self.db.execute(
            "UPDATE student SET score = 0 WHERE dept = 'eng';")
        self.assertEqual(result.rowcount, 4)
        self.assertEqual(
            self.db.query(
                "SELECT COUNT(*) FROM student WHERE score = 0;"),
            [(4,)])


class TestPersistence(TempDbCase):
    def test_data_survives_reopen(self) -> None:
        self.seed()
        self.db.execute("CREATE INDEX idx_dept ON student (dept);")
        before = self.db.query(
            "SELECT id, name, score FROM student ORDER BY id;")
        self.reopen()
        after = self.db.query(
            "SELECT id, name, score FROM student ORDER BY id;")
        self.assertEqual(before, after)
        # 重启后索引仍可用
        self.assertEqual(
            self.ids("SELECT id FROM student WHERE dept = 'eng';"),
            [1, 3, 5, 8])
        # 元数据（.schema 用的 DDL）也要活过重启
        ddl = self.db.schema("student")
        self.assertTrue(ddl[0].startswith("CREATE TABLE student"))
        self.assertIn("idx_dept", ddl[1])


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
