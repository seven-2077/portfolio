"""ingest.py 的单元测试：study-timer 读取、日报解析（含损坏输入）、按日对齐。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from learnlens.ingest import (
    ParseError,
    ingest_all,
    load_sessions,
    parse_report,
)
from learnlens.schema import write_json

GOOD_REPORT = """# 每日学习日报

> 2026-11-04（周三）收工总结

### 今日成果
数学做了强化课第三讲，408 刷了数据结构第六章的选择题。

### 明日三件事
给出明天最重要的三件具体事项，按优先级排列。

- [x] 数据结构第六章错题 15 道
- [-] 数学强化课第四讲
- [ ] 英语单词 Anki 200 张

### 今日自测
408 | 数据结构第六章选择 15 题 | 80%
math | 概率论第四章 | 0.75

### 一句话点评
进展可见，数学连续三天按时段推进。
"""


def make_report_text(tasks: str, tests: str) -> str:
    """按母版结构拼一份可定制的日报（tasks/tests 为小节正文）。"""
    return (
        "# 每日学习日报\n\n"
        "### 今日成果\n状态不错。\n\n"
        "### 明日三件事\n说明文字。\n\n" + tasks + "\n"
        "### 今日自测\n" + tests + "\n"
        "### 一句话点评\n继续。\n"
    )


class TestLoadSessions(unittest.TestCase):
    """study-timer log.json 的读取与按日/科目聚合。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, payload) -> Path:
        path = self.root / "log.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_missing_file_returns_empty(self):
        # study-timer 还没跑出数据是常态，不算错误
        self.assertEqual(load_sessions(self.root / "log.json"), {})

    def test_aggregates_by_day_and_subject(self):
        path = self._write([
            {"start": "2026-11-03T09:00", "end": "2026-11-03T11:00",
             "minutes": 120, "subject": "408", "note": ""},
            {"start": "2026-11-03T14:00", "end": "2026-11-03T15:30",
             "minutes": 90, "subject": "math", "note": ""},
            {"start": "2026-11-04T09:00", "end": "2026-11-04T10:00",
             "minutes": 60, "subject": "408", "note": ""},
        ])
        days = load_sessions(path)
        self.assertEqual(list(days), [date(2026, 11, 3), date(2026, 11, 4)])
        day3 = days[date(2026, 11, 3)]
        self.assertEqual(day3.total_minutes, 210.0)
        self.assertEqual(day3.minutes_by_subject(),
                         {"408": 120.0, "math": 90.0})
        self.assertEqual(len(day3.sessions), 2)

    def test_cross_midnight_counts_start_day(self):
        # 跨午夜的学习段归到开始那天（「昨晚学到凌晨」算昨天的投入）
        path = self._write([
            {"start": "2026-11-03T23:00", "end": "2026-11-04T00:30",
             "minutes": 90, "subject": "408", "note": ""},
        ])
        days = load_sessions(path)
        self.assertEqual(list(days), [date(2026, 11, 3)])

    def test_invalid_json_raises_parse_error(self):
        path = self.root / "log.json"
        path.write_text("{ broken", encoding="utf-8")
        with self.assertRaises(ParseError) as ctx:
            load_sessions(path)
        self.assertIn("JSON", str(ctx.exception))

    def test_non_list_top_level_rejected(self):
        path = self._write({"start": "2026-11-03T09:00"})
        with self.assertRaises(ParseError) as ctx:
            load_sessions(path)
        self.assertIn("数组", str(ctx.exception))

    def test_bad_entry_reports_index(self):
        path = self._write([
            {"start": "2026-11-03T09:00", "end": "2026-11-03T10:00",
             "minutes": 60, "subject": "408"},
            {"start": "2026-11-03T09:00", "end": "2026-11-03T10:00",
             "minutes": 60, "subject": ""},  # 空科目
        ])
        with self.assertRaises(ParseError) as ctx:
            load_sessions(path)
        self.assertIn("第 2 条", str(ctx.exception))


class TestParseReport(unittest.TestCase):
    """日报 Markdown 解析：正常样例、日期定位、各种损坏输入的报错。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, text: str, name: str = "2026-11-04.md") -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_full_report_parses(self):
        report = parse_report(self._write(GOOD_REPORT))
        self.assertEqual(report.day, date(2026, 11, 4))
        self.assertEqual([t.status for t in report.tasks],
                         ["done", "partial", "missed"])
        self.assertEqual(report.tasks[0].text, "数据结构第六章错题 15 道")
        self.assertEqual(len(report.self_tests), 2)
        self.assertEqual(report.self_tests[0].subject, "408")
        self.assertAlmostEqual(report.self_tests[0].accuracy, 80.0)
        # 小数写法 0.75 → 75%
        self.assertAlmostEqual(report.self_tests[1].accuracy, 75.0)
        self.assertEqual(report.self_tests[0].source, "report")
        self.assertAlmostEqual(report.execution_rate, 1 / 3)

    def test_date_from_content_when_filename_has_none(self):
        path = self._write(GOOD_REPORT, name="日报.md")
        report = parse_report(path)
        self.assertEqual(report.day, date(2026, 11, 4))

    def test_missing_date_anywhere_rejected(self):
        path = self._write(make_report_text("- [x] 事项", "今日无自测"),
                           name="日报.md")
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("日期", str(ctx.exception))

    def test_missing_tasks_section_rejected_with_line(self):
        text = make_report_text("", "今日无自测").replace(
            "### 明日三件事\n说明文字。\n\n\n", "")
        path = self._write(text, name="2026-11-04.md")
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("明日三件事", str(ctx.exception))
        self.assertIn("行", str(ctx.exception))

    def test_missing_selftest_section_rejected(self):
        text = make_report_text("- [x] 事项", "今日无自测").replace(
            "### 今日自测\n今日无自测\n", "")
        path = self._write(text, name="2026-11-04.md")
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("今日自测", str(ctx.exception))

    def test_bad_checkbox_marker_rejected_with_line_number(self):
        text = make_report_text(
            "- [x] 正常事项\n- [?] 手滑的标记", "今日无自测"
        )
        path = self._write(text)
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        message = str(ctx.exception)
        self.assertIn("checkbox", message)
        # make_report_text 拼出的文件里，坏标记位于第 10 行
        self.assertIn("行 10", message)

    def test_bad_accuracy_rejected_with_line_number(self):
        text = make_report_text("- [x] 正常事项", "408 | 第六章 | 八十分")
        path = self._write(text)
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        message = str(ctx.exception)
        self.assertIn("正确率", message)
        self.assertIn("行", message)

    def test_selftest_line_missing_pipes_rejected(self):
        text = make_report_text("- [x] 正常事项", "408 第六章 80%")
        path = self._write(text)
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("科目 | 章节 | 正确率", str(ctx.exception))

    def test_empty_tasks_section_rejected(self):
        text = make_report_text("（还没想好）", "今日无自测")
        path = self._write(text)
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("checkbox", str(ctx.exception))

    def test_no_selftest_marker_gives_empty_list(self):
        report = parse_report(
            self._write(make_report_text("- [x] 事项", "今日无自测")))
        self.assertEqual(report.self_tests, [])

    def test_status_comment_overrides_marker(self):
        # 母版：新计划写 `- [ ] # status: pending`，不能被误判成 missed
        text = make_report_text(
            "- [ ] 明天的第一件事            # status: pending\n"
            "- [x] 昨天的事",
            "今日无自测",
        )
        report = parse_report(self._write(text))
        self.assertEqual(report.tasks[0].status, "pending")
        self.assertNotIn("status:", report.tasks[0].text)
        self.assertEqual(report.tasks[1].status, "done")

    def test_unknown_status_comment_rejected(self):
        text = make_report_text("- [ ] 事项 # status: halfway", "今日无自测")
        path = self._write(text)
        with self.assertRaises(ParseError) as ctx:
            parse_report(path)
        self.assertIn("status", str(ctx.exception))

    def test_free_text_keeps_other_sections(self):
        report = parse_report(self._write(GOOD_REPORT))
        self.assertIn("今日成果", report.free_text)
        self.assertIn("一句话点评", report.free_text)
        self.assertNotIn("明日三件事", report.free_text)

    def test_empty_file_rejected(self):
        path = self._write("", name="2026-11-04.md")
        with self.assertRaises(ParseError):
            parse_report(path)


class TestIngestAll(unittest.TestCase):
    """三路数据按日对齐。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "reports").mkdir()

    def _write_log(self) -> None:
        write_json(self.root / "log.json", [
            {"start": "2026-11-04T09:00", "end": "2026-11-04T11:00",
             "minutes": 120, "subject": "408", "note": ""},
            {"start": "2026-11-05T09:00", "end": "2026-11-05T10:00",
             "minutes": 60, "subject": "math", "note": ""},
        ])

    def test_empty_dir_gives_empty_result(self):
        self.assertEqual(ingest_all(self.root), [])

    def test_aligns_sessions_report_and_manual_tests(self):
        self._write_log()
        (self.root / "reports" / "2026-11-04.md").write_text(
            GOOD_REPORT, encoding="utf-8")
        write_json(self.root / "selftest.json", [
            {"subject": "english", "section": "阅读 2 篇", "accuracy": 70,
             "date": "2026-11-05", "source": "manual"},
        ])

        records = ingest_all(self.root)
        self.assertEqual([r.day for r in records],
                         [date(2026, 11, 4), date(2026, 11, 5)])

        day4 = records[0]
        self.assertEqual(len(day4.sessions), 1)
        self.assertIsNotNone(day4.report)
        self.assertEqual(len(day4.self_tests), 2)  # 来自日报的两条

        day5 = records[1]
        self.assertIsNone(day5.report)  # 没日报的一天照样保留时长
        self.assertEqual(len(day5.self_tests), 1)
        self.assertEqual(day5.self_tests[0].source, "manual")
        self.assertEqual(day5.total_minutes, 60.0)

    def test_dedups_identical_test_across_sources(self):
        self._write_log()
        (self.root / "reports" / "2026-11-04.md").write_text(
            GOOD_REPORT, encoding="utf-8")
        # 手动录了与日报完全相同的一条 → 只应保留一份
        write_json(self.root / "selftest.json", [
            {"subject": "408", "section": "数据结构第六章选择 15 题",
             "accuracy": 80, "date": "2026-11-04", "source": "manual"},
        ])
        records = ingest_all(self.root)
        day4 = records[0]
        self.assertEqual(len(day4.self_tests), 2)  # 408 那条去重，math 保留

    def test_duplicate_day_report_keeps_first(self):
        (self.root / "reports" / "2026-11-04.md").write_text(
            GOOD_REPORT, encoding="utf-8")
        # 文件名排序时 "2026-11-04.md" 先于 "2026-11-04a.md"（'.' < 'a'）
        (self.root / "reports" / "2026-11-04a.md").write_text(
            GOOD_REPORT.replace("- [x]", "- [ ]"), encoding="utf-8")
        records = ingest_all(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].report.tasks[0].status, "done")

    def test_broken_report_aborts_with_location(self):
        (self.root / "reports" / "2026-11-04.md").write_text(
            make_report_text("- [x] 事项", "408 | 六章 | 九成"),  # 坏正确率
            encoding="utf-8")
        with self.assertRaises(ParseError) as ctx:
            ingest_all(self.root)
        self.assertIn("2026-11-04.md", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
