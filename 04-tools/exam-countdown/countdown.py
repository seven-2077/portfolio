#!/usr/bin/env python3
"""exam-countdown · 考研倒计时与阶段仪表（纯标准库，零依赖）。

    python countdown.py                       显示倒计时仪表
    python countdown.py --date 2027-12-19     换目标日期（确认初试日后用）
    python countdown.py --selftest            日期计算自检

日期说明：档案记录口述为 2027-11，但全国初试通常在 12 月倒数第二个周末，
默认值 2027-12-19 为推算值 —— 确认后用 --date 或改 CONFIG。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

# ---------- 配置（确认日期后改这里） ----------
EXAM_DATE = date(2027, 12, 19)      # 初试推算日（待官方确认）
RECRUIT_DATE = date(2027, 9, 15)    # 秋招「去看看」窗口，档案口径 2027-09
DAILY_TARGET_H = 4                  # 每日达标线（小时）

# 备考阶段（按日期自动切段，仅参考不焦虑）
PHASES = [
    (date(2026, 11, 1), date(2027, 2, 28), "基础收尾 · 强化启动"),
    (date(2027, 3, 1), date(2027, 6, 30), "强化主期 · 研究线维护"),
    (date(2027, 7, 1), date(2027, 8, 31), "暑期强化 · 全科滚动"),
    (date(2027, 9, 1), date(2027, 10, 31), "冲刺启动 · 秋招试探并行"),
    (date(2027, 11, 1), date(2027, 12, 18), "终极冲刺 · 模考复盘"),
]

BAR_WIDTH = 30


def days_between(today: date, target: date) -> int:
    return (target - today).days


def phase_of(today: date) -> str:
    for start, end, name in PHASES:
        if start <= today <= end:
            return name
    return "已完成初试" if today > PHASES[-1][1] else "未排期"


def exam_progress(today: date, exam: date = EXAM_DATE) -> float:
    """从考研优先起点（2026-11-01）到初试的总进度 0~1。"""
    origin = date(2026, 11, 1)
    total = (exam - origin).days
    elapsed = (today - origin).days
    if total <= 0:
        raise ValueError("考试日期须晚于起点")
    return elapsed / total


def progress_bar(ratio: float, width: int = BAR_WIDTH) -> str:
    ratio = max(0.0, min(ratio, 1.0))
    filled = int(ratio * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def render(today: date | None = None,
           exam: date = EXAM_DATE,
           recruit: date = RECRUIT_DATE) -> str:
    today = today or date.today()
    d_exam = days_between(today, exam)
    d_recruit = days_between(today, recruit)
    ratio = exam_progress(today, exam)
    weeks = d_exam / 7 if d_exam > 0 else 0

    lines = [
        "",
        f"  考研倒计时 · {exam:%Y-%m-%d}" +
        ("（日期待官方确认）" if exam == EXAM_DATE else ""),
        "",
        f"    距初试 {max(d_exam, 0)} 天 · 约 {weeks:.1f} 周",
        f"    总进度 {progress_bar(ratio)} {ratio * 100:.1f}%",
        f"    当前阶段：{phase_of(today)}",
        "",
    ]
    if d_recruit > 0:
        lines.append(f"    参照：距秋招窗口（{recruit:%Y-%m-%d}）{d_recruit} 天")
    else:
        lines.append("    参照：秋招窗口已过 / 进行中")

    now = datetime.now()
    hours_left = 24 - now.hour - now.minute / 60
    lines += [
        f"    今日：剩余 {hours_left:.1f} 小时，达标线 {DAILY_TARGET_H}h"
        "（study-timer 记着呢）",
        "",
    ]
    return "\n".join(lines)


def selftest() -> int:
    assert days_between(date(2026, 11, 4), date(2026, 11, 5)) == 1
    assert days_between(date(2026, 11, 4), date(2026, 11, 4)) == 0
    assert phase_of(date(2026, 11, 4)) == "基础收尾 · 强化启动"
    assert phase_of(date(2027, 7, 15)) == "暑期强化 · 全科滚动"
    assert phase_of(date(2027, 12, 20)) == "已完成初试"
    assert abs(exam_progress(date(2026, 11, 1))) < 1e-9   # 起点为 0
    assert exam_progress(EXAM_DATE) == 1.0                 # 初试日为 1
    assert progress_bar(0.5).count("█") == BAR_WIDTH // 2
    assert progress_bar(2.0).count("█") == BAR_WIDTH        # 封顶
    out = render(today=date(2026, 11, 4))
    assert "距初试" in out and "总进度" in out
    print("✓ selftest 通过（日期差 / 阶段切换 / 进度封顶 / 渲染）")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="countdown",
                                     description="考研倒计时仪表")
    parser.add_argument("--date", default=None,
                        help="初试日期 YYYY-MM-DD（确认后传入或改 CONFIG）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    exam = EXAM_DATE
    if args.date:
        try:
            exam = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("日期格式应为 YYYY-MM-DD，如 2027-12-19")
            return 1
    print(render(exam=exam))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
