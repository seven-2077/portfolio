"""测试公共设施：临时目录、数据库句柄、重启与崩溃模拟。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from minidb import Database

#: 种子数据：10 行 student（eng 4 / hr 3 / ops 3，分数 64~96）
SEED_SQL = """
CREATE TABLE student (
  id INT PRIMARY KEY,
  name TEXT NOT NULL,
  dept TEXT,
  score FLOAT
);
INSERT INTO student VALUES (1, 'Alice', 'eng', 92.5);
INSERT INTO student VALUES (2, 'Bob', 'hr', 87.0);
INSERT INTO student VALUES (3, 'Carol', 'eng', 95.5);
INSERT INTO student VALUES (4, 'Dan', 'ops', 71.0);
INSERT INTO student VALUES (5, 'Eve', 'eng', 88.0);
INSERT INTO student VALUES (6, 'Frank', 'hr', 79.5);
INSERT INTO student VALUES (7, 'Grace', 'ops', 91.0);
INSERT INTO student VALUES (8, 'Heidi', 'eng', 64.0);
INSERT INTO student VALUES (9, 'Ivan', 'hr', 83.5);
INSERT INTO student VALUES (10, 'Judy', 'ops', 96.0);
"""


class TempDbCase(unittest.TestCase):
    """每个用例独立临时目录 + 全新数据库文件。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="minidb_test_"))
        self.db_path = self.tmp / "test.db"
        self.db = Database(self.db_path)

    def tearDown(self) -> None:
        try:
            self.db.kill()     # 不触发提交：测试里的脏页本就该被丢弃
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- 辅助 ---------------------------------------------------------------

    def reopen(self) -> Database:
        """模拟进程重启：杀掉旧句柄再打开（触发启动恢复）。"""
        self.db.kill()
        self.db = Database(self.db_path)
        return self.db

    def seed(self) -> None:
        """灌入 SEED_SQL（10 行 student）。"""
        self.db.executescript(SEED_SQL)

    def ids(self, sql: str) -> list[int]:
        """执行 SELECT 并取第一列（惯例用 id 列），方便断言。"""
        return [row[0] for row in self.db.query(sql)]

    def wal_size(self) -> int:
        wal = self.db_path.with_name(self.db_path.name + ".wal")
        return wal.stat().st_size if wal.exists() else -1
