"""pet.studylink — 彩蛋：用 study-timer 的学习数据当「宠物食物」。

约定接口（只读！）：读 04-tools/study-timer/data/log.json，条目形如
{"start": ISO串, "minutes": 90.0, "subject": "408", ...}；统计今日
minutes 总和按 4h 目标折算喂食加成（0~50%）。文件不存在/损坏时回退
内置演示数据，绝不写对方目录。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

STUDY_DIR = Path(
    r"C:\Users\Seven\DeskBox\AI Tools\Cursor Workplace\04-tools\study-timer")
LOG_FILE = STUDY_DIR / "data" / "log.json"

DEMO_MINUTES = 300.0        # 内置演示数据：今天学了 5 小时
DAILY_TARGET = 240.0        # 每日 4h 目标（与 study-timer 一致）
MAX_BONUS = 0.5             # 加成封顶 +50%


@dataclass(frozen=True)
class StudyReport:
    minutes: float       # 今日学习分钟数
    source: str          # "study-timer" | "demo"
    bonus: float         # 喂食加成 0~0.5
    log_path: str        # 数据来源路径（demo 时为 ""）


def feeding_bonus(minutes: float, target: float = DAILY_TARGET) -> float:
    """学习时长 → 喂食加成：按 4h 目标线性折算，封顶 +50%。"""
    if minutes <= 0 or target <= 0:
        return 0.0
    return round(min(minutes / target, 1.0) * MAX_BONUS, 4)


def today_minutes(entries, today: date) -> float:
    """从 log.json 的条目列表里筛出今天的分钟总数（坏条目静默跳过）。"""
    total = 0.0
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            start = datetime.fromisoformat(str(item["start"]))
            minutes = float(item["minutes"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.date() == today and minutes > 0:
            total += minutes
    return round(total, 1)


def load_report(now: datetime | None = None,
                log_path: str | Path | None = None) -> StudyReport:
    """读学习数据生成报告；读不到就用演示数据，永不抛异常。"""
    now = now or datetime.now()
    path = Path(log_path) if log_path else LOG_FILE
    minutes = DEMO_MINUTES
    source = "demo"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                minutes = today_minutes(data, now.date())
                source = "study-timer"
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    return StudyReport(minutes=minutes, source=source,
                       bonus=feeding_bonus(minutes),
                       log_path=str(path) if source == "study-timer" else "")


def format_minutes(minutes: float) -> str:
    """332.5 → '5h32m'。"""
    total = int(round(minutes))
    return f"{total // 60}h{total % 60:02d}m"
