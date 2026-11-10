"""schema.py 的单元测试：构造校验、正确率解析、JSON 序列化往返。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from learnlens.schema import (
    TASK_STATUSES,
    DailyReport,
    SchemaError,
    SelfTest,
    StudySession,
    TaskItem,
    load_records,
    parse_accuracy,
    read_json,
    save_records,
    write_json,
)


class TestStudySession(unittest.TestCase):
    """StudySession 构造与反序列化校验。"""

    def _valid(self) -> StudySession:
        return StudySession(
            start=datetime(2026, 11, 4, 9, 0),
            end=datetime(2026, 11, 4, 10, 30),
            minutes=90.0,
            subject="408",
            note="数据结构",
        )

    def test_valid_session_roundtrip(self):
        session = self._valid()
        again = StudySession.from_dict(session.to_dict())
        self.assertEqual(again, session)
        self.assertEqual(again.day, date(2026, 11, 4))

    def test_end_before_start_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            StudySession(
                start=datetime(2026, 11, 4, 10, 0),
                end=datetime(2026, 11, 4, 9, 0),
                minutes=60,
                subject="math",
            )
        self.assertIn("end", str(ctx.exception))

    def test_negative_minutes_rejected(self):
        with self.assertRaises(SchemaError):
            StudySession(
                start=datetime(2026, 11, 4, 9, 0),
                end=datetime(2026, 11, 4, 10, 0),
                minutes=-5,
                subject="math",
            )

    def test_empty_subject_rejected(self):
        with self.assertRaises(SchemaError):
            StudySession(
                start=datetime(2026, 11, 4, 9, 0),
                end=datetime(2026, 11, 4, 10, 0),
                minutes=60,
                subject="   ",
            )

    def test_from_dict_missing_field(self):
        with self.assertRaises(SchemaError) as ctx:
            StudySession.from_dict(
                {"start": "2026-11-04T09:00", "end": "2026-11-04T10:00",
                 "minutes": 60}
            )
        self.assertIn("subject", str(ctx.exception))

    def test_from_dict_bad_iso_time(self):
        with self.assertRaises(SchemaError) as ctx:
            StudySession.from_dict(
                {"start": "昨天早上", "end": "2026-11-04T10:00",
                 "minutes": 60, "subject": "408"}
            )
        self.assertIn("start", str(ctx.exception))

    def test_from_dict_minutes_must_be_number(self):
        with self.assertRaises(SchemaError):
            StudySession.from_dict(
                {"start": "2026-11-04T09:00", "end": "2026-11-04T10:00",
                 "minutes": "六十", "subject": "408"}
            )

    def test_from_dict_non_object_rejected(self):
        with self.assertRaises(SchemaError):
            StudySession.from_dict(["not", "a", "dict"])


class TestParseAccuracy(unittest.TestCase):
    """人类输入 → 0-100 百分数的规范化。"""

    def test_percent_and_plain_number(self):
        self.assertEqual(parse_accuracy("80%"), 80.0)
        self.assertEqual(parse_accuracy("80"), 80.0)
        self.assertEqual(parse_accuracy(85), 85.0)

    def test_fraction_notation(self):
        # ≤1 的数按比例记：0.85 是最常见的小数写法，不能读成 0.85%
        self.assertEqual(parse_accuracy("0.85"), 85.0)
        self.assertEqual(parse_accuracy(0.8), 80.0)
        self.assertEqual(parse_accuracy("1"), 100.0)

    def test_whitespace_and_full_width_percent(self):
        self.assertEqual(parse_accuracy("  75 % "), 75.0)

    def test_invalid_text_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            parse_accuracy("良好")
        self.assertIn("80%", str(ctx.exception))

    def test_out_of_range_rejected(self):
        with self.assertRaises(SchemaError):
            parse_accuracy("150%")
        with self.assertRaises(SchemaError):
            parse_accuracy("-3")

    def test_bool_rejected(self):
        # bool 是 int 的子类，True 会被误读成 1 → 100%，必须显式拒绝
        with self.assertRaises(SchemaError):
            parse_accuracy(True)


class TestTaskItem(unittest.TestCase):
    """三件事条目状态校验。"""

    def test_default_status_is_pending(self):
        self.assertEqual(TaskItem(text="背单词").status, "pending")
        self.assertEqual(set(TASK_STATUSES),
                         {"pending", "done", "partial", "missed"})

    def test_valid_statuses_accepted(self):
        for status in TASK_STATUSES:
            item = TaskItem(text="刷题", status=status)
            self.assertEqual(item.status, status)

    def test_invalid_status_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            TaskItem(text="刷题", status="half")  # type: ignore[arg-type]
        self.assertIn("half", str(ctx.exception))

    def test_empty_text_rejected(self):
        with self.assertRaises(SchemaError):
            TaskItem(text="  ")

    def test_counted_excludes_pending(self):
        self.assertFalse(TaskItem(text="新计划").counted)
        self.assertTrue(TaskItem(text="旧计划", status="missed").counted)


class TestSelfTest(unittest.TestCase):
    """自测条目校验与序列化。"""

    def test_accuracy_bounds(self):
        base = dict(subject="408", section="第六章", day=date(2026, 11, 4))
        SelfTest(accuracy=100.0, **base)  # 边界值合法
        with self.assertRaises(SchemaError):
            SelfTest(accuracy=101.0, **base)
        with self.assertRaises(SchemaError):
            SelfTest(accuracy=-0.5, **base)

    def test_roundtrip_serializes_date_as_iso(self):
        test = SelfTest(subject="math", section="概率第四章",
                        accuracy=76.5, day=date(2026, 11, 4))
        payload = test.to_dict()
        self.assertEqual(payload["date"], "2026-11-04")
        self.assertEqual(SelfTest.from_dict(payload), test)

    def test_from_dict_missing_fields(self):
        with self.assertRaises(SchemaError) as ctx:
            SelfTest.from_dict({"subject": "408", "date": "2026-11-04"})
        self.assertIn("section", str(ctx.exception))

    def test_from_dict_bad_date(self):
        with self.assertRaises(SchemaError):
            SelfTest.from_dict(
                {"subject": "408", "section": "第六章",
                 "accuracy": 80, "date": "11/04"}
            )


class TestDailyReport(unittest.TestCase):
    """整份日报的组装、执行率与序列化。"""

    def _report(self) -> DailyReport:
        return DailyReport(
            day=date(2026, 11, 4),
            tasks=[
                TaskItem(text="错题 15 道", status="done"),
                TaskItem(text="强化课一讲", status="partial"),
                TaskItem(text="Anki 200 张", status="missed"),
                TaskItem(text="明天的新计划", status="pending"),
            ],
            self_tests=[
                SelfTest(subject="408", section="第六章", accuracy=80.0,
                         day=date(2026, 11, 4), source="report"),
            ],
            free_text="### 今日成果\n今天状态不错",
            source="2026-11-04.md",
        )

    def test_execution_rate_excludes_pending(self):
        # 分母只算回看过的 3 条，pending 不算「没完成」
        self.assertAlmostEqual(self._report().execution_rate, 1 / 3)

    def test_execution_rate_none_without_reviewed_tasks(self):
        report = DailyReport(day=date(2026, 11, 4),
                             tasks=[TaskItem(text="新计划")])
        self.assertIsNone(report.execution_rate)

    def test_full_roundtrip(self):
        report = self._report()
        again = DailyReport.from_dict(report.to_dict())
        self.assertEqual(again, report)
        self.assertEqual(again.free_text, report.free_text)

    def test_from_dict_missing_date(self):
        with self.assertRaises(SchemaError) as ctx:
            DailyReport.from_dict({"tasks": [], "self_tests": []})
        self.assertIn("date", str(ctx.exception))

    def test_from_dict_rejects_non_task_entries(self):
        with self.assertRaises(SchemaError):
            DailyReport.from_dict(
                {"date": "2026-11-04", "tasks": [{"oops": 1}],
                 "self_tests": []}
            )


class TestJsonIO(unittest.TestCase):
    """JSON 读写与记录列表的落盘/回读。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_write_read_roundtrip_chinese_preserved(self):
        path = self.root / "nested" / "x.json"
        write_json(path, {"科目": "408", "值": [1, 2]})
        self.assertEqual(read_json(path), {"科目": "408", "值": [1, 2]})

    def test_read_json_invalid_raises_with_path(self):
        path = self.root / "bad.json"
        path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(SchemaError) as ctx:
            read_json(path)
        self.assertIn("bad.json", str(ctx.exception))

    def test_load_records_missing_file_returns_empty(self):
        self.assertEqual(load_records(self.root / "none.json", SelfTest), [])

    def test_load_records_reports_bad_index(self):
        path = self.root / "tests.json"
        write_json(path, [
            {"subject": "408", "section": "第六章", "accuracy": 80,
             "date": "2026-11-04"},
            {"subject": "408", "section": "第七章", "accuracy": 80,
             "date": "not-a-date"},
        ])
        with self.assertRaises(SchemaError) as ctx:
            load_records(path, SelfTest)
        self.assertIn("第 2 条", str(ctx.exception))

    def test_save_load_records_roundtrip(self):
        path = self.root / "selftest.json"
        records = [
            SelfTest(subject="math", section="第三章", accuracy=90.0,
                     day=date(2026, 11, 5)),
            SelfTest(subject="english", section="阅读 2 篇", accuracy=75.0,
                     day=date(2026, 11, 5), source="report"),
        ]
        save_records(path, records)
        self.assertEqual(load_records(path, SelfTest), records)


if __name__ == "__main__":
    unittest.main()
