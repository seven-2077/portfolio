"""周聚合：周一起算的逐日汇总、执行率与自测统计。

与 CLI 分离的原因：聚合是研究结论的算术来源，必须能在测试里被逐项钉死；
CLI 只负责取数和排版，两者混在一起就没法对「执行率到底怎么算」做单元测试。

口径约定（对应 RESEARCH-PLAN 的 RQ1/RQ2）：

- 一周从**周一**开始（考研作息按自然周复盘，周日做总结时「本周」含当天）；
- 执行率 = done / 已回看数，``pending``（还没到回看时点的新计划）不进分母 ——
  把未回看的计划算作未完成，等于惩罚「还没发生的事」，会系统性低估执行率；
- 部分完成 ``partial`` 计入分母但不计入分子（严格口径），另单独给出计数，
  让「差一点就完成」这种信息不被一个百分比吃掉。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .ingest import DayRecord

__all__ = [
    "week_bounds",
    "DaySummary",
    "WeekSummary",
    "build_week",
]


def week_bounds(today: date) -> tuple[date, date]:
    """返回包含 ``today`` 的自然周的 (周一, 周日)。"""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


@dataclass
class DaySummary:
    """某一天的汇总视图（含无数据的占位日，表格才不会断行）。"""

    day: date
    minutes: float = 0.0
    subjects: dict[str, float] = field(default_factory=dict)
    tasks_done: int = 0
    tasks_partial: int = 0
    tasks_missed: int = 0
    tasks_pending: int = 0
    selftest_count: int = 0
    accuracies: list[float] = field(default_factory=list)

    @property
    def tasks_total(self) -> int:
        """已回看的任务数（执行率分母），pending 不计。"""
        return self.tasks_done + self.tasks_partial + self.tasks_missed

    @property
    def execution_rate(self) -> float | None:
        """当日执行率；一条都没回看时为 None（区别于 0.0）。"""
        if self.tasks_total == 0:
            return None
        return self.tasks_done / self.tasks_total

    @property
    def avg_accuracy(self) -> float | None:
        """当日平均正确率；无自测时为 None。"""
        if not self.accuracies:
            return None
        return round(sum(self.accuracies) / len(self.accuracies), 1)


def _summarize(record: DayRecord | None, day: date) -> DaySummary:
    """把（可能缺失的）DayRecord 压成 DaySummary。"""
    if record is None:
        return DaySummary(day=day)
    summary = DaySummary(
        day=day,
        minutes=round(sum(s.minutes for s in record.sessions), 1),
        selftest_count=len(record.self_tests),
        accuracies=[t.accuracy for t in record.self_tests],
    )
    bucket: dict[str, float] = {}
    for session in record.sessions:
        bucket[session.subject] = round(
            bucket.get(session.subject, 0.0) + session.minutes, 1
        )
    summary.subjects = bucket
    for task in (record.report.tasks if record.report else []):
        if task.status == "done":
            summary.tasks_done += 1
        elif task.status == "partial":
            summary.tasks_partial += 1
        elif task.status == "missed":
            summary.tasks_missed += 1
        else:
            summary.tasks_pending += 1
    return summary


@dataclass
class WeekSummary:
    """一周（周一起 7 天）的完整汇总。"""

    start: date
    end: date
    days: list[DaySummary] = field(default_factory=list)

    @property
    def total_minutes(self) -> float:
        return round(sum(d.minutes for d in self.days), 1)

    @property
    def total_selftests(self) -> int:
        return sum(d.selftest_count for d in self.days)

    @property
    def all_accuracies(self) -> list[float]:
        out: list[float] = []
        for d in self.days:
            out.extend(d.accuracies)
        return out

    @property
    def avg_accuracy(self) -> float | None:
        """全周平均正确率（按自测条目简单平均，不做科目加权 —— 条目数还少）。"""
        values = self.all_accuracies
        if not values:
            return None
        return round(sum(values) / len(values), 1)

    @property
    def overall_execution_rate(self) -> float | None:
        """全周执行率：全周 done / 全周已回看数（按条目汇总，不是 7 天率的平均）。"""
        total = sum(d.tasks_total for d in self.days)
        if total == 0:
            return None
        done = sum(d.tasks_done for d in self.days)
        return done / total

    @property
    def total_tasks(self) -> int:
        return sum(d.tasks_total for d in self.days)

    @property
    def total_done(self) -> int:
        return sum(d.tasks_done for d in self.days)

    @property
    def subject_totals(self) -> dict[str, float]:
        """全周科目总时长，按投入降序。"""
        bucket: dict[str, float] = {}
        for d in self.days:
            for subject, minutes in d.subjects.items():
                bucket[subject] = round(bucket.get(subject, 0.0) + minutes, 1)
        return dict(sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0])))


def build_week(records: list[DayRecord], today: date) -> WeekSummary:
    """把按日对齐的记录截成本周（周一~周日）的 :class:`WeekSummary`。

    只取落在周界内的记录；无数据的日期也占位（minutes=0、rate=None），
    这样终端表格永远是整齐的 7 行，缺数据一眼可见而不是行错位。
    """
    monday, sunday = week_bounds(today)
    by_day = {r.day: r for r in records if monday <= r.day <= sunday}
    days = [
        _summarize(by_day.get(monday + timedelta(days=i)),
                   monday + timedelta(days=i))
        for i in range(7)
    ]
    return WeekSummary(start=monday, end=sunday, days=days)
