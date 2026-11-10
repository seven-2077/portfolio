"""weekly.py 的单元测试：周界、执行率口径、汇总算术。"""

from __future__ import annotations

import unittest
from datetime import date

from learnlens.ingest import DayRecord
from learnlens.schema import DailyReport, SelfTest, StudySession, TaskItem
from learnlens.weekly import build_week, week_bounds


def session(day: date, minutes: float, subject: str = "408") -> StudySession:
    from datetime import datetime, timedelta
    start = datetime(day.year, day.month, day.day, 9, 0)
    return StudySession(start=start,
                        end=start + timedelta(minutes=minutes),
                        minutes=minutes, subject=subject)


class TestWeekBounds(unittest.TestCase):
    """周一起算的边界。"""

    def test_wednesday_maps_to_monday(self):
        monday, sunday = week_bounds(date(2026, 11, 4))  # 周三
        self.assertEqual(monday, date(2026, 11, 2))
        self.assertEqual(sunday, date(2026, 11, 8))

    def test_monday_is_week_start(self):
        monday, sunday = week_bounds(date(2026, 11, 2))  # 周一
        self.assertEqual(monday, date(2026, 11, 2))
        self.assertEqual(sunday, date(2026, 11, 8))

    def test_sunday_stays_in_same_week(self):
        # 周日复盘时「本周」必须含当天，不能跳到下周一
        monday, sunday = week_bounds(date(2026, 11, 8))  # 周日
        self.assertEqual(monday, date(2026, 11, 2))
        self.assertEqual(sunday, date(2026, 11, 8))


class TestBuildWeek(unittest.TestCase):
    """按日记录 → 周汇总。"""

    def test_empty_records_gives_seven_placeholder_days(self):
        summary = build_week([], date(2026, 11, 4))
        self.assertEqual(len(summary.days), 7)
        self.assertEqual(summary.total_minutes, 0.0)
        self.assertIsNone(summary.overall_execution_rate)
        self.assertIsNone(summary.avg_accuracy)

    def test_days_outside_week_are_ignored(self):
        records = [
            DayRecord(day=date(2026, 11, 1),  # 上周日
                      sessions=[session(date(2026, 11, 1), 600)]),
            DayRecord(day=date(2026, 11, 9),  # 下周一
                      sessions=[session(date(2026, 11, 9), 600)]),
        ]
        summary = build_week(records, date(2026, 11, 4))
        self.assertEqual(summary.total_minutes, 0.0)

    def test_minutes_and_subjects_aggregated(self):
        records = [
            DayRecord(day=date(2026, 11, 3), sessions=[
                session(date(2026, 11, 3), 120, "408"),
                session(date(2026, 11, 3), 60, "408"),
                session(date(2026, 11, 3), 90, "math"),
            ]),
        ]
        summary = build_week(records, date(2026, 11, 4))
        tuesday = summary.days[1]
        self.assertEqual(tuesday.day, date(2026, 11, 3))
        self.assertEqual(tuesday.minutes, 270.0)
        self.assertEqual(tuesday.subjects, {"408": 180.0, "math": 90.0})
        self.assertEqual(summary.total_minutes, 270.0)
        self.assertEqual(summary.subject_totals, {"408": 180.0, "math": 90.0})

    def test_execution_rate_counts_done_over_reviewed(self):
        report = DailyReport(
            day=date(2026, 11, 3),
            tasks=[
                TaskItem(text="a", status="done"),
                TaskItem(text="b", status="done"),
                TaskItem(text="c", status="partial"),
                TaskItem(text="d", status="missed"),
                TaskItem(text="e", status="pending"),  # 不进分母
            ],
        )
        summary = build_week([DayRecord(day=date(2026, 11, 3), report=report)],
                             date(2026, 11, 4))
        tuesday = summary.days[1]
        self.assertEqual(tuesday.tasks_total, 4)
        self.assertEqual(tuesday.tasks_pending, 1)
        self.assertAlmostEqual(tuesday.execution_rate, 0.5)
        # 全周口径按条目汇总，不是 7 天率的平均
        self.assertAlmostEqual(summary.overall_execution_rate, 0.5)
        self.assertEqual(summary.total_tasks, 4)
        self.assertEqual(summary.total_done, 2)

    def test_rate_none_when_no_reviewed_tasks(self):
        report = DailyReport(day=date(2026, 11, 3),
                             tasks=[TaskItem(text="新计划")])
        summary = build_week([DayRecord(day=date(2026, 11, 3), report=report)],
                             date(2026, 11, 4))
        self.assertIsNone(summary.days[1].execution_rate)
        self.assertEqual(summary.days[1].tasks_pending, 1)

    def test_selftest_stats(self):
        records = [
            DayRecord(day=date(2026, 11, 3), self_tests=[
                SelfTest(subject="408", section="第六章", accuracy=80.0,
                         day=date(2026, 11, 3)),
                SelfTest(subject="math", section="第三章", accuracy=70.0,
                         day=date(2026, 11, 3)),
            ]),
            DayRecord(day=date(2026, 11, 5), self_tests=[
                SelfTest(subject="english", section="阅读", accuracy=90.0,
                         day=date(2026, 11, 5)),
            ]),
        ]
        summary = build_week(records, date(2026, 11, 4))
        self.assertEqual(summary.total_selftests, 3)
        self.assertEqual(summary.days[1].selftest_count, 2)
        self.assertAlmostEqual(summary.days[1].avg_accuracy, 75.0)
        self.assertEqual(summary.days[3].selftest_count, 1)
        self.assertAlmostEqual(summary.avg_accuracy, 80.0)
        # 没自测的日子 avg 为 None（而非 0）
        self.assertIsNone(summary.days[0].avg_accuracy)

    def test_day_record_without_sessions(self):
        summary = build_week([DayRecord(day=date(2026, 11, 4))],
                             date(2026, 11, 4))
        wednesday = summary.days[2]
        self.assertEqual(wednesday.minutes, 0.0)
        self.assertIsNone(wednesday.execution_rate)


if __name__ == "__main__":
    unittest.main()
