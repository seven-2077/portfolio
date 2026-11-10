#!/usr/bin/env python3
"""study-timer — 考研学习时长记录与目标进度工具（纯标准库，零依赖）。

用法速览：
    python study_timer.py start 408 [备注]     开始一段学习，科目 408
    python study_timer.py stop                 结束当前段并入库
    python study_timer.py add --minutes 90 --subject math [备注]
    python study_timer.py today                今日统计 + 目标进度条
    python study_timer.py week                 本周逐日统计
    python study_timer.py pomodoro 25 5        番茄钟（学习25 休息5，循环）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
LOG_FILE = DATA_DIR / "log.json"
STATE_FILE = DATA_DIR / "state.json"

# 每日总学习目标区间（小时），来自个人档案：每天总计 4-8h
DAILY_TARGET_MIN = 4 * 60
DAILY_STRETCH_MIN = 8 * 60

BAR_WIDTH = 30


@dataclass
class Entry:
    start: str          # ISO 时间串
    end: str            # ISO 时间串
    minutes: float      # 时长（分钟）
    subject: str        # 科目：408 / math / english / politics / other
    note: str = ""


@dataclass
class State:
    """running 状态：start 命令写下，stop 命令读取并结算。"""

    running: bool = False
    start: str = ""
    subject: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)


# ---------- 存储层 ----------

def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, payload) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_entries() -> list[Entry]:
    raw = _load_json(LOG_FILE, [])
    return [Entry(**item) for item in raw]


def save_entries(entries: list[Entry]) -> None:
    _save_json(LOG_FILE, [asdict(e) for e in entries])


def load_state() -> State:
    raw = _load_json(STATE_FILE, {})
    return State(**raw) if raw else State()


def save_state(state: State) -> None:
    _save_json(STATE_FILE, asdict(state))


# ---------- 业务逻辑 ----------

def add_entry(entries: list[Entry], start: datetime, end: datetime,
              subject: str, note: str = "") -> list[Entry]:
    """追加一条记录。end 必须晚于 start，时长截断为非负。"""
    if end < start:
        raise ValueError("结束时间不能早于开始时间")
    minutes = round((end - start).total_seconds() / 60, 1)
    entries.append(Entry(
        start=start.isoformat(timespec="minutes"),
        end=end.isoformat(timespec="minutes"),
        minutes=minutes,
        subject=subject or "other",
        note=note,
    ))
    return entries


def entries_on(entries: list[Entry], day: date) -> list[Entry]:
    return [e for e in entries if datetime.fromisoformat(e.start).date() == day]


def sum_minutes(entries: list[Entry]) -> float:
    return round(sum(e.minutes for e in entries), 1)


def week_entries(entries: list[Entry], today: date) -> dict[date, float]:
    """本周（周一起）逐日分钟数。"""
    monday = today - timedelta(days=today.weekday())
    result: dict[date, float] = {}
    for i in range(7):
        day = monday + timedelta(days=i)
        result[day] = sum_minutes(entries_on(entries, day))
    return result


def subject_breakdown(entries: list[Entry]) -> dict[str, float]:
    bucket: dict[str, float] = {}
    for e in entries:
        bucket[e.subject] = round(bucket.get(e.subject, 0) + e.minutes, 1)
    return dict(sorted(bucket.items(), key=lambda kv: -kv[1]))


def progress_bar(minutes: float, target: float = DAILY_TARGET_MIN,
                 width: int = BAR_WIDTH) -> str:
    """目标进度条：达到 4h 满一格，冲 8h 用百分比继续计。"""
    if target <= 0:
        raise ValueError("目标必须为正")
    ratio = minutes / target
    filled = min(int(ratio * width), width)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(ratio * 100)
    if minutes >= DAILY_STRETCH_MIN:
        return f"[{bar}] {pct}% · 已达 8h 上限区"
    return f"[{bar}] {pct}%"


# ---------- 命令实现 ----------

def cmd_start(subject: str, note: str) -> None:
    state = load_state()
    if state.running:
        print(f"已有一段在计时（{state.subject} 起于 {state.start}），"
              f"先 stop 再开新的。")
        return
    save_state(State(running=True, start=datetime.now().isoformat(
        timespec="seconds"), subject=subject or "other", note=note))
    print(f"▶ 开始：{subject or 'other'} {('｜' + note) if note else ''}"
          f"  {datetime.now():%H:%M:%S}")


def cmd_stop() -> None:
    state = load_state()
    if not state.running:
        print("当前没有进行中的学习段。")
        return
    start = datetime.fromisoformat(state.start)
    end = datetime.now()
    entries = load_entries()
    add_entry(entries, start, end, state.subject, state.note)
    save_entries(entries)
    save_state(State())
    minutes = round((end - start).total_seconds() / 60, 1)
    today_min = sum_minutes(entries_on(entries, date.today()))
    print(f"■ 结束：{state.subject} 本次 {minutes} 分钟")
    print(f"  今日累计 {today_min} 分钟  {progress_bar(today_min)}")


def cmd_add(minutes: float, subject: str, note: str,
            start: str | None = None) -> None:
    if minutes <= 0:
        raise ValueError("时长必须为正数")
    end = datetime.now()
    begin = (datetime.strptime(start, "%H:%M").replace(
        year=end.year, month=end.month, day=end.day)
        if start else end - timedelta(minutes=minutes))
    entries = load_entries()
    add_entry(entries, begin, begin + timedelta(minutes=minutes),
              subject, note)
    save_entries(entries)
    today_min = sum_minutes(entries_on(entries, date.today()))
    print(f"✓ 已补录 {minutes} 分钟（{subject}）")
    print(f"  今日累计 {today_min} 分钟  {progress_bar(today_min)}")


def cmd_today() -> None:
    entries = entries_on(load_entries(), date.today())
    minutes = sum_minutes(entries)
    print(f"今日 {date.today():%Y-%m-%d} 学习记录")
    print(f"  总计 {minutes} 分钟（{minutes / 60:.1f} h）  "
          f"{progress_bar(minutes)}")
    print("  目标区间：4h 达标 / 8h 上限")
    if entries:
        print("  明细：")
        for e in entries:
            print(f"    {e.start[11:16]}-{e.end[11:16]}  "
                  f"{e.minutes:>6.1f}min  {e.subject}"
                  f"{('  ' + e.note) if e.note else ''}")
        print("  科目分布：")
        for sub, mins in subject_breakdown(entries).items():
            print(f"    {sub:<10} {mins:>6.1f} min")
    else:
        print("  还没有记录 —— start 开一段，或 add 补录。")


def cmd_week() -> None:
    entries = load_entries()
    grid = week_entries(entries, date.today())
    total = round(sum(grid.values()), 1)
    print(f"本周学习（周一起，共 {total / 60:.1f} h / 目标 {7 * 4}h+）")
    for day, mins in grid.items():
        h = int(mins // 60)
        m = int(mins % 60)
        mark = "✓" if mins >= DAILY_TARGET_MIN else ("~" if mins > 0 else "·")
        print(f"  {day:%m-%d} {day:%a}  {mark} {h:>2}h{m:02d}m  "
              f"{progress_bar(mins)}")


def cmd_pomodoro(work_min: int, break_min: int) -> None:
    print(f"番茄钟：学 {work_min} 分钟 · 休 {break_min} 分钟（Ctrl+C 结束）")
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"\n🍅 第 {cycle} 个番茄 —— {work_min}:00 后提醒休息")
            _countdown(work_min * 60, "学习")
            entries = load_entries()
            now = datetime.now()
            add_entry(entries, now - timedelta(minutes=work_min), now,
                      "pomodoro", f"#{cycle}")
            save_entries(entries)
            print(f"  已记录 {work_min} 分钟。休息 {break_min} 分钟～")
            _countdown(break_min * 60, "休息")
    except KeyboardInterrupt:
        print("\n番茄钟结束，进度已保存。")


def _countdown(seconds: int, label: str) -> None:
    remain = seconds
    while remain > 0:
        mm, ss = divmod(remain, 60)
        sys.stdout.write(f"\r  {label} {mm:02d}:{ss:02d} ")
        sys.stdout.flush()
        time.sleep(1)
        remain -= 1
    print()


# ---------- CLI ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="study_timer",
        description="考研学习时长记录与 4-8h 目标进度工具")
    sub = p.add_subparsers(dest="cmd")

    ps = sub.add_parser("start", help="开始一段学习")
    ps.add_argument("subject", nargs="?", default="", help="科目")
    ps.add_argument("note", nargs="?", default="", help="备注")

    sub.add_parser("stop", help="结束当前学习段")

    pa = sub.add_parser("add", help="补录一段时长")
    pa.add_argument("--minutes", "-m", type=float, required=True)
    pa.add_argument("--subject", "-s", default="other")
    pa.add_argument("--start", default=None, help="开始时刻 HH:MM，默认现在往前推")
    pa.add_argument("note", nargs="?", default="")

    sub.add_parser("today", help="今日统计")
    sub.add_parser("week", help="本周逐日统计")

    pp = sub.add_parser("pomodoro", help="番茄钟循环")
    pp.add_argument("work", type=int, nargs="?", default=25)
    pp.add_argument("rest", type=int, nargs="?", default=5)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "start":
            cmd_start(args.subject, args.note)
        elif args.cmd == "stop":
            cmd_stop()
        elif args.cmd == "add":
            cmd_add(args.minutes, args.subject, args.note, args.start)
        elif args.cmd == "today":
            cmd_today()
        elif args.cmd == "week":
            cmd_week()
        elif args.cmd == "pomodoro":
            cmd_pomodoro(args.work, args.rest)
        else:
            build_parser().print_help()
    except ValueError as exc:
        print(f"错误：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
