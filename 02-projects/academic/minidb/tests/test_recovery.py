"""崩溃恢复测试：注入故障点模拟进程被 kill，重开后验证数据完好。

对应 WAL 提交协议的四个阶段（wal.py 文档 ①②③④）::

    before_commit   崩在 ① 之前  -> 语句未提交，重开后**丢失**（正确语义）
    after_commit    崩在 ②~③    -> 日志已持久，重开后 redo **补齐**
    mid_writes      崩在 ③ 中途  -> 半截数据页，重开后 redo **修复**
    before_truncate 崩在 ④ 之前  -> 数据已全写，redo **幂等**重放无副作用
"""

from __future__ import annotations

from support import TempDbCase

from minidb import SimulatedCrash


class TestCrashRecovery(TempDbCase):
    def _crash_at(self, failpoint: str, sql: str) -> None:
        """注入故障点 -> 执行 sql（提交时崩溃）-> 模拟进程被杀。"""
        self.db.inject_failpoint(failpoint)
        with self.assertRaises(SimulatedCrash):
            self.db.execute(sql)
        self.db.kill()

    def test_clean_close_truncates_wal(self) -> None:
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self.db.execute("INSERT INTO t VALUES (1);")
        self.assertEqual(self.wal_size(), 0)     # 每次提交后日志归零
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,)])

    def test_crash_before_commit_loses_statement(self) -> None:
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self.db.execute("INSERT INTO t VALUES (1);")
        # 崩在提交点之前：语句本来就没算数，重开后必须丢弃
        self._crash_at("before_commit", "INSERT INTO t VALUES (2);")
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,)])

    def test_crash_after_commit_recovers(self) -> None:
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self.db.execute("INSERT INTO t VALUES (1);")
        self._crash_at("after_commit", "INSERT INTO t VALUES (2);")
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,), (2,)])

    def test_crash_mid_writes_recovers(self) -> None:
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY, pad TEXT);")
        self.db.execute("INSERT INTO t VALUES (1, 'aaaa');")
        self._crash_at(
            "mid_writes",
            "INSERT INTO t VALUES (2, 'bbbb'), (3, 'cccc'), (4, 'dddd');")
        self.reopen()
        rows = self.db.query("SELECT id FROM t ORDER BY id;")
        self.assertEqual(rows, [(1,), (2,), (3,), (4,)])

    def test_crash_before_truncate_recovers(self) -> None:
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self.db.execute("INSERT INTO t VALUES (1);")
        self._crash_at("before_truncate", "INSERT INTO t VALUES (2);")
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,), (2,)])

    def test_repeated_reopen_is_idempotent(self) -> None:
        # redo 幂等：连开三次结果都一样
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self._crash_at("after_commit", "INSERT INTO t VALUES (1);")
        for _ in range(3):
            self.reopen()
            self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,)])

    def test_torn_wal_tail_is_ignored(self) -> None:
        # 崩溃可能留下撕裂的半条记录：CRC 校验必须把它截断，
        # 但不能连累它之前已提交的内容
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self._crash_at("after_commit", "INSERT INTO t VALUES (1);")
        wal = self.db_path.with_name(self.db_path.name + ".wal")
        with open(wal, "ab") as f:
            f.write(b"\x01\x02\x03garbage-tail")   # 模拟写了一半的记录
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,)])
        self.assertEqual(self.wal_size(), 0)         # 恢复后日志被清空

    def test_constraint_failure_rolls_back_before_commit(self) -> None:
        # 普通错误（非崩溃）走 rollback：日志与缓冲一起丢
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY);")
        self.db.execute("INSERT INTO t VALUES (1);")
        from minidb.errors import DuplicateKeyError
        with self.assertRaises(DuplicateKeyError):
            self.db.execute("INSERT INTO t VALUES (1);")
        self.assertEqual(self.wal_size(), 0)         # 回滚把日志清了
        self.reopen()
        self.assertEqual(self.db.query("SELECT id FROM t;"), [(1,)])

    def test_ddl_also_goes_through_wal(self) -> None:
        # 建表/建索引的元数据页与数据页同一次提交（不撕裂）
        self.db.execute("CREATE TABLE t (id INT PRIMARY KEY, v INT);")
        self.db.execute("CREATE INDEX idx_v ON t (v);")
        self.db.execute("INSERT INTO t VALUES (1, 10), (2, 20);")
        self._crash_at("after_commit", "INSERT INTO t VALUES (3, 30);")
        self.reopen()
        self.assertEqual(
            self.db.query("SELECT id FROM t WHERE v = 30;"), [(3,)])
        _, indexes = self.db.catalog_names()
        self.assertEqual(indexes, ["idx_v"])


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
