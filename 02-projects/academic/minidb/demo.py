#!/usr/bin/env python3
"""端到端演示：建表 -> 插入 30 行 -> 查询/聚合 -> 模拟崩溃 -> 重启验证持久化。

运行::

    python demo.py

演示脚本刻意把「崩溃」也走了一遍：注入 after_commit 故障点后进程被 kill，
重启时可以看到 WAL redo 恢复的真实输出。
"""

from __future__ import annotations

import sys
from pathlib import Path

from minidb import SimulatedCrash, connect
from minidb.repl import format_table

DB = Path(__file__).parent / "demo.db"

NAMES = [
    "Alice", "Bob", "Carol", "Dan", "Eve", "Frank", "Grace", "Heidi", "Ivan",
    "Judy", "Mallory", "Niaj", "Olivia", "Peggy", "Rupert", "Sybil", "Trent",
    "Victor", "Walter", "Zoe", "Dave", "Elsa", "Finn", "Gina", "Hugo", "Iris",
    "Jack", "Karen", "Leo", "Mia",
]
DEPTS = ["eng", "hr", "ops", "sales"]


def banner(title: str) -> None:
    print(f"\n{'=' * 66}\n  {title}\n{'=' * 66}")


def show_select(db, sql: str) -> None:
    print(sql.strip())
    result = db.execute(sql)
    print(format_table(result.columns, result.rows))


def build_rows() -> str:
    lines = []
    for i in range(30):
        name = NAMES[i]
        dept = DEPTS[i % len(DEPTS)]
        score = 55 + (i * 7) % 46          # 55 ~ 100，确定性生成
        lines.append(f"INSERT INTO student VALUES "
                     f"({i + 1}, '{name}', '{dept}', {score}.0);")
    return "\n".join(lines)


def main() -> int:
    # 每次演示从干净状态开始
    for suffix in ("", ".wal"):
        p = Path(str(DB) + suffix)
        if p.exists():
            p.unlink()

    banner("1. 建表 + 二级索引")
    db = connect(DB)
    print(db.execute(
        "CREATE TABLE student ("
        " id INT PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " dept TEXT,"
        " score FLOAT"
        ");").message)
    print(db.execute(
        "CREATE INDEX idx_dept ON student (dept);").message)

    banner("2. 插入 30 行（多语句脚本）")
    results = db.executescript(build_rows())
    print(f"执行 {len(results)} 条 INSERT，"
          f"共插入 {sum(r.rowcount for r in results)} 行")

    banner("3. 查询：WHERE 过滤 + ORDER BY + LIMIT")
    show_select(db,
                "SELECT id, name, dept, score FROM student"
                " WHERE dept = 'eng' AND score >= 80"
                " ORDER BY score DESC LIMIT 5;")

    banner("4. 聚合：GROUP BY + COUNT/AVG/MIN/MAX")
    show_select(db,
                "SELECT dept, COUNT(*), AVG(score) FROM student"
                " GROUP BY dept ORDER BY dept;")

    banner("5. EXPLAIN：存取路径选择（主键索引 vs 二级索引）")
    print("WHERE id = 7（主键等值 -> 主键索引）:")
    print(db.execute(
        "EXPLAIN SELECT name FROM student WHERE id = 7;").plan_text)
    print("\nWHERE dept = 'eng'（二级索引最左前缀等值）:")
    print(db.execute(
        "EXPLAIN SELECT name FROM student WHERE dept = 'eng';").plan_text)
    print("\n无索引可用（全表顺序扫描）:")
    print(db.execute(
        "EXPLAIN SELECT name FROM student WHERE score > 95;").plan_text)

    banner("6. 模拟崩溃：提交点之后、数据页回写之前被 kill")
    db.inject_failpoint("after_commit")
    try:
        db.execute("INSERT INTO student VALUES (99, 'CrashKid', 'eng', 100.0);")
    except SimulatedCrash:
        print("  [模拟] 进程在 after_commit 处被 kill")
        print("  此时：WAL 已带 COMMIT 落盘，数据页还没回写")
    db.kill()

    banner("7. 重启：启动时 WAL redo 恢复（注意上方 [minidb] 输出）")
    db = connect(DB)
    row = db.query("SELECT id, name FROM student WHERE id = 99;")
    print(f"  崩溃前已提交的第 99 行: {row}   -> 已由 redo 补齐")
    (count,) = db.query("SELECT COUNT(*) FROM student;")[0]
    print(f"  总行数: {count}（30 行原始数据 + 1 行崩溃前提交）")

    banner("8. 再次重启：正常关闭后的持久化验证")
    db.close()
    db = connect(DB)
    (count2,) = db.query("SELECT COUNT(*) FROM student;")[0]
    print(f"  重启后行数: {count2}，与关闭前一致 -> 数据完好")
    show_select(db,
                "SELECT id, name, score FROM student"
                " ORDER BY score DESC LIMIT 3;")

    db.close()
    wal = Path(str(DB) + ".wal")
    print(f"\n  WAL 文件大小: {wal.stat().st_size} 字节"
          "（checkpoint 后日志已归零）")
    print("\n演示完成。交互式体验：python -m minidb demo.db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
