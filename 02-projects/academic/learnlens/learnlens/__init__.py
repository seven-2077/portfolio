"""LearnLens —— 考研备考过程的数据研究管道（纯标准库，零依赖）。

计划书见 ``RESEARCH-PLAN.md``；本包实现第一期：schema → ingest → weekly → cli。
"""

from __future__ import annotations

from .schema import (
    TASK_STATUSES,
    DailyReport,
    SchemaError,
    SelfTest,
    StudySession,
    TaskItem,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SchemaError",
    "StudySession",
    "TaskItem",
    "SelfTest",
    "DailyReport",
    "TASK_STATUSES",
]
