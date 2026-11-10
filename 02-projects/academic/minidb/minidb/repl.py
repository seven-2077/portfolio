"""交互式 REPL —— 分号多语句缓冲 + 点元命令。

设计要点：

* **语句缓冲**：输入累积到「最后一个 token 是 ``;``」才执行，
  天然支持跨行语句与一次粘贴多条语句（:func:`minidb.tokenizer.is_complete`）。
  字符串没闭合时 :class:`~minidb.errors.UnterminatedStringError` 会让
  调用方继续读入下一行 —— 这正是 sqlite3 的行为。
* **元命令以 ``.`` 开头**，与 SQL 语法空间隔离（`.` 不是 SQL 运算符）。
* **可注入 I/O**：stdin/stdout 从构造参数进，测试用 StringIO
  就能完整驱动 REPL，不必起子进程。

用法::

    python -m minidb                # 打开当前目录 minidb.db
    python -m minidb path/to/x.db   # 指定库文件
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence, TextIO

from .database import Database, Result
from .errors import MiniDBError, UnterminatedStringError

BANNER = """\
minidb 0.1.0 · 教学型嵌入式 SQL 数据库（纯 Python 标准库）
输入 SQL 以 ; 结尾后回车执行；.help 查看元命令；.quit 退出。"""

HELP = """\
元命令：
  .tables              列出所有表
  .schema [表名]       显示建表语句（不带表名则显示全部）
  .indexes             列出非主键索引
  .crash <故障点>      注入崩溃故障点（演示 WAL 恢复用），可选：
                       before_commit / after_commit / mid_writes / before_truncate
  .help                显示本帮助
  .quit / .exit        退出

SQL 语句以英文分号 ; 结尾，可跨行续写，也可一次粘贴多条语句。"""


def format_table(columns: list[str], rows: list[tuple]) -> str:
    """把查询结果排成对齐的表格（数值列右对齐，NULL 单独标记）。"""

    def fmt(v: object) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, float):
            # 整数值的浮点显示成 3.0 而非 3.0000000001
            return repr(v)
        return str(v)

    def is_numeric(col_idx: int) -> bool:
        return all(
            r[col_idx] is None or isinstance(r[col_idx], (int, float))
            for r in rows
        ) and any(
            isinstance(r[col_idx], (int, float)) for r in rows
        )

    cells = [[fmt(v) for v in row] for row in rows]
    widths = [len(c) for c in columns]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(char: str = "-") -> str:
        return "+" + "+".join(char * (w + 2) for w in widths) + "+"

    def render(cells_: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells_):
            if is_numeric(i):
                parts.append(cell.rjust(widths[i]))
            else:
                parts.append(cell.ljust(widths[i]))
        return "| " + " | ".join(parts) + " |"

    out = [line(), render(columns), line()]
    out += [render(row) for row in cells]
    out.append(line())
    out.append(f"({len(rows)} 行)")
    return "\n".join(out)


class Repl:
    """REPL 主循环。stdin/stdout 可注入，便于测试。"""

    def __init__(self, db: Database,
                 stdin: Optional[TextIO] = None,
                 stdout: Optional[TextIO] = None) -> None:
        self.db = db
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self._buffer = ""

    # -- I/O 基元 -----------------------------------------------------------

    def _write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.flush()

    def _println(self, text: str = "") -> None:
        self._write(text + "\n")

    def _readline(self, prompt: str) -> str:
        self._write(prompt)
        line = self.stdin.readline()
        if line == "":           # EOF（Ctrl+Z 回车 / 管道结束）
            raise EOFError
        return line.rstrip("\r\n")

    # -- 主循环 -------------------------------------------------------------

    def run(self) -> int:
        """跑 REPL 直到 EOF / .quit。返回进程退出码。"""
        self._println(BANNER)
        while True:
            prompt = "minidb> " if not self._buffer else "   ...> "
            try:
                line = self._readline(prompt)
            except EOFError:
                self._println()
                break
            except KeyboardInterrupt:
                self._println("^C")
                self._buffer = ""
                continue

            # 点命令只在「没有未完成语句」时识别，否则它是 SQL 的一部分
            if not self._buffer and line.lstrip().startswith("."):
                if not self._meta(line.strip()):
                    break
                continue

            self._buffer += line + "\n"
            if not self._buffer.strip():
                self._buffer = ""
                continue

            status = self._try_execute(self._buffer)
            if status == "more":
                continue        # 语句未以 ; 收尾 / 字符串未闭合 -> 续行
            self._buffer = ""

        return 0

    def _try_execute(self, sql: str) -> str:
        """尝试执行缓冲区。返回 ``done`` / ``more``。"""
        from .tokenizer import is_complete

        try:
            complete = is_complete(sql)
        except UnterminatedStringError:
            return "more"       # 字符串还没闭合：等下一行
        if not complete:
            return "more"       # 还没见到结尾的 ;
        try:
            for result in self.db.executescript(sql):
                self._println(self._render(result))
        except MiniDBError as exc:
            self._println(f"错误: {exc}")
        except Exception as exc:  # pragma: no cover - 防御性兜底
            self._println(f"内部错误: {type(exc).__name__}: {exc}")
        return "done"

    # -- 结果渲染 -----------------------------------------------------------

    def _render(self, result: Result) -> str:
        if result.kind == "select":
            if not result.columns:
                return "(0 行)"
            return format_table(result.columns, result.rows)
        if result.kind == "explain":
            return result.plan_text
        return result.message

    # -- 元命令 -------------------------------------------------------------

    def _meta(self, line: str) -> bool:
        """执行点命令。返回 False 表示 REPL 应当退出。"""
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        try:
            if cmd in (".quit", ".exit"):
                return False
            if cmd == ".help":
                self._println(HELP)
            elif cmd == ".tables":
                tables, _ = self.db.catalog_names()
                if not tables:
                    self._println("(没有表)")
                else:
                    self._println(f"tables ({len(tables)}): "
                                 + ", ".join(tables))
            elif cmd == ".indexes":
                _, indexes = self.db.catalog_names()
                if not indexes:
                    self._println("(没有二级索引)")
                else:
                    self._println(f"indexes ({len(indexes)}): "
                                 + ", ".join(indexes))
            elif cmd == ".schema":
                stmts = self.db.schema(args[0] if args else None)
                if not stmts:
                    self._println("(没有匹配的 DDL)")
                for s in stmts:
                    self._println(s)
            elif cmd == ".crash":
                if len(args) != 1:
                    self._println("用法: .crash <故障点>  （.help 查看可选值）")
                else:
                    self.db.inject_failpoint(args[0])
                    self._println(f"已注入故障点 {args[0]}："
                                  "下一次提交将在此处「崩溃」")
            else:
                self._println(f"未知元命令 {cmd}（.help 查看帮助）")
        except MiniDBError as exc:
            self._println(f"错误: {exc}")
        return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    """REPL 进程入口：``python -m minidb [数据库文件]``。"""
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else Path("minidb.db")
    try:
        db = Database(path)
    except MiniDBError as exc:
        print(f"无法打开数据库 {path}: {exc}", file=sys.stderr)
        return 1
    try:
        return Repl(db).run()
    finally:
        db.close()


if __name__ == "__main__":      # pragma: no cover
    raise SystemExit(main())
