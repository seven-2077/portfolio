"""learnlens 命令行：录自测、解析日报、出周汇总。

三个子命令对应三种使用场景，全部围绕「低摩擦」设计：

- ``log-test`` —— 30 秒录一条自测，自动盖今天日期，错一个字才报错；
- ``report``   —— 给一份日报文件或目录，打印结构化摘要核对解析结果；
- ``week``     —— 本周汇总表格，收工时扫一眼。

聚合算术全部放在 :mod:`learnlens.weekly`，本模块只做取数与排版。
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date
from pathlib import Path

from .ingest import (
    DayRecord,
    DaySessions,
    ParseError,
    ingest_all,
    load_sessions,
    parse_report,
)
from .schema import (
    DailyReport,
    SchemaError,
    SelfTest,
    load_records,
    parse_accuracy,
    save_records,
)
from .weekly import WeekSummary, build_week

__all__ = ["main", "build_parser"]

#: 自测数据的默认落盘位置（研究数据与代码分离，data/ 已在 .gitignore）
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
SELFTEST_FILE = "selftest.json"

_WEEKDAY_CN = "一二三四五六日"
_STATUS_MARK = {"done": "✓", "partial": "~", "missed": "✗", "pending": "○"}


# ---------- 基础设施 ----------

def _ensure_utf8() -> None:
    """Windows 下输出被重定向到管道时默认用 locale 编码，中文/符号可能崩；
    强制 UTF-8，失败则保持平台默认（不打断命令）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


def resolve_log_path(data_dir: Path, explicit: Path | None) -> Path:
    """定位 study-timer 的 log.json。

    优先级：``--log`` 显式指定 > ``<data_dir>/log.json`` > 沿当前目录向上找
    工作区里的 ``04-tools/study-timer/data/log.json``（默认布局）。
    都找不到时返回 data_dir 下的约定路径 —— load_sessions 对不存在的文件
    返回空，不报错（study-timer 还没跑出数据是常态）。
    """
    if explicit is not None:
        return explicit
    candidate = data_dir / "log.json"
    if candidate.exists():
        return candidate
    here = Path.cwd()
    for base in (here, *here.parents):
        found = base / "04-tools" / "study-timer" / "data" / "log.json"
        if found.exists():
            return found
    return candidate


def _fmt_minutes(minutes: float) -> str:
    """分钟 → ``4h20m``，小于 1 小时显示 ``55m``。"""
    if minutes <= 0:
        return "—"
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h{mins:02d}m"


def _fmt_rate(rate: float | None) -> str:
    """执行率 → ``67%``；无数据 → ``—``。"""
    if rate is None:
        return "—"
    return f"{rate * 100:.0f}%"


# ---------- 子命令：log-test ----------

def cmd_log_test(args: argparse.Namespace) -> int:
    """录一条自测：``log-test <科目> <章节> <正确率>``，自动盖今天日期。"""
    accuracy = parse_accuracy(args.accuracy)
    record = SelfTest(
        subject=args.subject,
        section=args.section,
        accuracy=accuracy,
        day=date.today(),
        source="manual",
    )
    path = args.data_dir / SELFTEST_FILE
    records: list[SelfTest] = load_records(path, SelfTest)
    records.append(record)
    save_records(path, records)
    print(
        f"✓ 已记录 {record.day} ｜ {record.subject} ｜ {record.section}"
        f" ｜ {record.accuracy:g}%（累计 {len(records)} 条）"
    )
    return 0


# ---------- 子命令：report ----------

def _print_report_summary(
    report: DailyReport, sessions_day: DaySessions | None
) -> None:
    """打印单份日报的结构化摘要。"""
    print(f"\n━━━ {report.day}（周{_WEEKDAY_CN[report.day.weekday()]}）日报 ━━━")
    rate = report.execution_rate
    counted = [t for t in report.tasks if t.counted]
    if counted:
        print(f"三件事：{_fmt_rate(rate)} 完成"
              f"（{sum(1 for t in counted if t.status == 'done')}"
              f"/{len(counted)}，回看 {len(counted)} 条"
              + (f"，另有 {len(report.tasks) - len(counted)} 条未回看"
                 if len(report.tasks) != len(counted) else "")
              + "）")
        for task in report.tasks:
            mark = _STATUS_MARK[task.status]
            suffix = f"  [{task.status}]" if task.status == "partial" else ""
            print(f"  {mark} {task.text}{suffix}")
    else:
        print("三件事：尚无回看记录（新计划 pending，不计入执行率）")

    if report.self_tests:
        print(f"自测：{len(report.self_tests)} 条")
        for test in report.self_tests:
            print(f"  · {test.subject} | {test.section} | {test.accuracy:g}%")
    else:
        print("自测：今日无自测")

    if sessions_day is not None and sessions_day.sessions:
        total = sessions_day.total_minutes
        print(f"当日时长：{total:.1f} min（{total / 60:.1f} h）")
        breakdown = " · ".join(
            f"{sub} {mins:g} min" for sub, mins in sessions_day.minutes_by_subject().items()
        )
        print(f"  {breakdown}")
    else:
        print("当日时长：无 study-timer 记录")


def cmd_report(args: argparse.Namespace) -> int:
    """解析日报文件或目录并打印摘要。"""
    target: Path = args.path
    if target.is_dir():
        files = sorted(target.glob("*.md"))
        if not files:
            print(f"错误：{target} 下没有 .md 日报", file=sys.stderr)
            return 1
    elif target.is_file():
        files = [target]
    else:
        print(f"错误：找不到 {target}", file=sys.stderr)
        return 1

    sessions = load_sessions(resolve_log_path(args.data_dir, args.log))
    failed = False
    for md in files:
        try:
            report = parse_report(md)
        except ParseError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            failed = True
            continue
        _print_report_summary(report, sessions.get(report.day))
    if len(files) > 1:
        print(f"\n共解析 {len(files)} 份日报"
              + ("（有失败，见上方错误）" if failed else "，全部成功"))
    return 1 if failed else 0


# ---------- 子命令：week ----------

def _display_width(text: str) -> int:
    """终端显示宽度：全角字符占 2 列 —— 直接用 len() 补空格会让中文列错位。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in text)


def _pad(text: str, width: int) -> str:
    """按显示宽度左对齐补齐。"""
    fill = width - _display_width(text)
    return text + " " * fill if fill > 0 else text


def _render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """零依赖终端表格：列宽取表头与所有单元格显示宽度的最大值。"""
    widths = [
        max([_display_width(h)] + [_display_width(row[i]) for row in rows])
        for i, h in enumerate(headers)
    ]
    gap = "  "
    lines = [gap.join(_pad(h, w) for h, w in zip(headers, widths)).rstrip()]
    lines.append("─" * (sum(widths) + gap.count(" ") * (len(widths) - 1)))
    for row in rows:
        lines.append(gap.join(_pad(str(c), w)
                              for c, w in zip(row, widths)).rstrip())
    return lines


def _print_week(summary: WeekSummary, today: date) -> None:
    """打印本周汇总表（终端表格，零依赖手排版）。"""
    print(f"本周汇总 {summary.start}（周{_WEEKDAY_CN[summary.start.weekday()]}）"
          f" ~ {summary.end}（周{_WEEKDAY_CN[summary.end.weekday()]}）"
          f"｜ 今天 {today}")
    headers = ["日期", "星期", "时长", "执行率", "自测", "平均正确率"]
    rows: list[list[str]] = []
    for day in summary.days:
        rate = "—" if day.tasks_total == 0 else (
            f"{_fmt_rate(day.execution_rate)}（{day.tasks_done}/{day.tasks_total}）"
        )
        rows.append([
            day.day.isoformat() + (" ←今天" if day.day == today else ""),
            _WEEKDAY_CN[day.day.weekday()],
            _fmt_minutes(day.minutes),
            rate,
            str(day.selftest_count),
            "—" if day.avg_accuracy is None else f"{day.avg_accuracy:g}%",
        ])
    for line in _render_table(headers, rows):
        print(line)
    print(f"合计：时长 {_fmt_minutes(summary.total_minutes)}"
          f"（{summary.total_minutes / 60:.1f} h）"
          f" ｜ 执行率 {_fmt_rate(summary.overall_execution_rate)}"
          f"（{summary.total_done}/{summary.total_tasks}）"
          f" ｜ 自测 {summary.total_selftests} 次"
          f" ｜ 平均正确率 "
          + ("—" if summary.avg_accuracy is None
             else f"{summary.avg_accuracy:g}%"))
    if summary.subject_totals:
        parts = " · ".join(
            f"{sub} {_fmt_minutes(mins)}"
            for sub, mins in summary.subject_totals.items()
        )
        print(f"科目分布：{parts}")


def cmd_week(args: argparse.Namespace) -> int:
    """本周汇总：每日时长、执行率、自测次数与平均正确率。"""
    records: list[DayRecord] = ingest_all(
        args.data_dir, log_path=resolve_log_path(args.data_dir, args.log)
    )
    today = date.today()
    summary = build_week(records, today)
    if not any(d.minutes or d.tasks_total or d.selftest_count for d in summary.days):
        print(f"本周（{summary.start} ~ {summary.end}）暂无数据 —— "
              "先跑几段 study-timer、录几条自测，或把日报放进 "
              f"{args.data_dir / 'reports'}。")
        return 0
    _print_week(summary, today)
    return 0


# ---------- CLI 骨架 ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="learnlens",
        description="考研备考过程的数据管道：录自测、解析日报、出周汇总",
    )
    sub = parser.add_subparsers(dest="cmd")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"数据目录（log.json / reports / selftest.json），默认 {DEFAULT_DATA_DIR}",
    )
    common.add_argument(
        "--log", type=Path, default=None,
        help="study-timer log.json 路径（默认自动查找）",
    )

    p_log = sub.add_parser(
        "log-test", parents=[common],
        help="30 秒录一条自测：log-test <科目> <章节> <正确率>",
    )
    p_log.add_argument("subject", help="科目，如 408 / math / english")
    p_log.add_argument("section", help="章节或卷号，如 数据结构第六章")
    p_log.add_argument(
        "accuracy", help="正确率：80%%、80、0.8 三种写法均可",
    )

    p_report = sub.add_parser(
        "report", parents=[common],
        help="解析日报并打印结构化摘要",
    )
    p_report.add_argument("path", type=Path, help="日报 .md 文件或所在目录")

    sub.add_parser(
        "week", parents=[common],
        help="本周汇总表（周一起算）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """入口：解析参数并分发；数据错误统一以「错误：…」打到 stderr 返回 1。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    _ensure_utf8()
    try:
        if args.cmd == "log-test":
            return cmd_log_test(args)
        if args.cmd == "report":
            return cmd_report(args)
        if args.cmd == "week":
            return cmd_week(args)
        parser.print_help()
        return 0
    except (SchemaError, ParseError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
