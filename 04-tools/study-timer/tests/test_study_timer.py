"""study-timer 核心逻辑测试（unittest，零依赖）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import study_timer as st


def entry(day: date, minutes: float, subject: str = "408",
          hour: int = 9) -> st.Entry:
    start = datetime(day.year, day.month, day.day, hour, 0)
    end = start + timedelta(minutes=minutes)
    return st.Entry(start=start.isoformat(timespec="minutes"),
                    end=end.isoformat(timespec="minutes"),
                    minutes=minutes, subject=subject)


class AddEntryTest(unittest.TestCase):
    def test_duration_computed(self):
        entries: list[st.Entry] = []
        st.add_entry(entries, datetime(2026, 11, 4, 9, 0),
                     datetime(2026, 11, 4, 10, 30), "math")
        self.assertEqual(entries[0].minutes, 90.0)

    def test_negative_duration_rejected(self):
        with self.assertRaises(ValueError):
            st.add_entry([], datetime(2026, 11, 4, 10, 0),
                         datetime(2026, 11, 4, 9, 0), "math")

    def test_empty_subject_defaults_to_other(self):
        entries: list[st.Entry] = []
        st.add_entry(entries, datetime(2026, 11, 4, 9, 0),
                     datetime(2026, 11, 4, 9, 30), "")
        self.assertEqual(entries[0].subject, "other")


class AggregationTest(unittest.TestCase):
    def setUp(self):
        self.fri = date(2026, 11, 6)          # 周五
        self.entries = [
            entry(self.fri, 60, "408"),
            entry(self.fri, 45, "math"),
            entry(self.fri - timedelta(days=4), 120, "english"),  # 周一
        ]

    def test_entries_on_filters_by_day(self):
        today = st.entries_on(self.entries, self.fri)
        self.assertEqual(len(today), 2)
        self.assertEqual(st.sum_minutes(today), 105.0)

    def test_week_starts_monday(self):
        grid = st.week_entries(self.entries, self.fri)
        self.assertEqual(len(grid), 7)
        monday = self.fri - timedelta(days=4)
        self.assertEqual(grid[monday], 120.0)
        # 上周日（11-01）不属于本周网格
        self.assertNotIn(date(2026, 11, 1), grid)

    def test_subject_breakdown_sorted_desc(self):
        breakdown = st.subject_breakdown(self.entries)
        # 降序：english 120 > 408 60 > math 45
        self.assertEqual(list(breakdown), ["english", "408", "math"])
        self.assertEqual(breakdown["math"], 45.0)


class ProgressBarTest(unittest.TestCase):
    def test_empty_bar(self):
        self.assertIn("░" * st.BAR_WIDTH, st.progress_bar(0))

    def test_full_at_target(self):
        bar = st.progress_bar(4 * 60)
        self.assertIn("█" * st.BAR_WIDTH, bar)
        self.assertIn("100%", bar)

    def test_three_quarters(self):
        self.assertIn("75%", st.progress_bar(3 * 60))

    def test_stretch_zone_marked(self):
        self.assertIn("8h 上限区", st.progress_bar(8 * 60))

    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            st.progress_bar(10, target=0)


class CliIntegrationTest(unittest.TestCase):
    """把数据目录指到临时区，跑 add → today 全链路。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [
            patch.object(st, "DATA_DIR", data),
            patch.object(st, "LOG_FILE", data / "log.json"),
            patch.object(st, "STATE_FILE", data / "state.json"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_add_then_today(self):
        code = st.main(["add", "-m", "90", "-s", "408", "数据结构"])
        self.assertEqual(code, 0)
        entries = st.load_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].subject, "408")

    def test_add_rejects_nonpositive(self):
        code = st.main(["add", "-m", "0"])
        self.assertEqual(code, 1)

    def test_stop_without_start_is_graceful(self):
        self.assertEqual(st.main(["stop"]), 0)   # 打印提示而非崩溃


if __name__ == "__main__":
    unittest.main(verbosity=2)
