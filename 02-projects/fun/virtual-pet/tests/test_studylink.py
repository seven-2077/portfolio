"""studylink 彩蛋：今日时长解析、加成计算、演示数据回退。"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from pet import studylink

NOW = datetime(2026, 3, 10, 12, 0)

ENTRIES = [
    {"start": "2026-03-10T08:00", "end": "2026-03-10T09:30",
     "minutes": 90.0, "subject": "408", "note": ""},
    {"start": "2026-03-10T14:00", "end": "2026-03-10T16:00",
     "minutes": 120.0, "subject": "math", "note": ""},
    {"start": "2026-03-09T08:00", "end": "2026-03-09T13:00",
     "minutes": 300.0, "subject": "english", "note": "昨天的"},
]


class TestParsing(unittest.TestCase):
    def test_today_minutes_sums_only_today(self):
        total = studylink.today_minutes(ENTRIES, NOW.date())
        self.assertAlmostEqual(total, 210.0)

    def test_bad_entries_skipped_without_crash(self):
        bad = [None, 42, "字符串", {"minutes": 60},          # 缺 start
               {"start": "不是时间", "minutes": 60},          # 坏时间
               {"start": "2026-03-10T08:00", "minutes": "abc"},
               {"start": "2026-03-10T08:00", "minutes": -30}]
        self.assertAlmostEqual(studylink.today_minutes(bad, NOW.date()), 0.0)


class TestBonusCurve(unittest.TestCase):
    def test_bonus_scales_with_minutes_and_caps(self):
        self.assertEqual(studylink.feeding_bonus(0), 0.0)
        self.assertEqual(studylink.feeding_bonus(-100), 0.0)
        self.assertAlmostEqual(studylink.feeding_bonus(120), 0.25)   # 2h → +25%
        self.assertAlmostEqual(studylink.feeding_bonus(240), 0.5)    # 4h → +50%
        self.assertAlmostEqual(studylink.feeding_bonus(9999), 0.5)   # 封顶

    def test_format_minutes(self):
        self.assertEqual(studylink.format_minutes(90), "1h30m")
        self.assertEqual(studylink.format_minutes(0), "0h00m")
        self.assertEqual(studylink.format_minutes(61), "1h01m")


class TestLoadReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "log.json"
        self.addCleanup(self._tmp.cleanup)

    def test_missing_file_falls_back_to_demo(self):
        report = studylink.load_report(now=NOW, log_path=self.log)
        self.assertEqual(report.source, "demo")
        self.assertEqual(report.minutes, studylink.DEMO_MINUTES)
        self.assertAlmostEqual(report.bonus, 0.5)

    def test_corrupt_file_falls_back_to_demo(self):
        self.log.write_text("{broken json", encoding="utf-8")
        report = studylink.load_report(now=NOW, log_path=self.log)
        self.assertEqual(report.source, "demo")
        self.assertEqual(report.minutes, studylink.DEMO_MINUTES)

    def test_real_file_parsed_with_bonus(self):
        self.log.write_text(json.dumps(ENTRIES, ensure_ascii=False),
                            encoding="utf-8")
        report = studylink.load_report(now=NOW, log_path=self.log)
        self.assertEqual(report.source, "study-timer")
        self.assertAlmostEqual(report.minutes, 210.0)
        self.assertAlmostEqual(report.bonus, 0.4375)     # 210/240*0.5
        self.assertIn("log.json", report.log_path)

    def test_non_list_payload_falls_back_to_demo(self):
        self.log.write_text('{"not": "a list"}', encoding="utf-8")
        report = studylink.load_report(now=NOW, log_path=self.log)
        self.assertEqual(report.source, "demo")


if __name__ == "__main__":
    unittest.main()
