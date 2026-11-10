"""cli.py 的全链路测试：三个子命令在临时目录里端到端跑通。"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from learnlens.cli import main
from learnlens.schema import SelfTest, load_records, write_json

TODAY = date.today()


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """跑一次 CLI，返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def report_text(day: date, tasks: str = "- [x] 背完第六章\n- [-] 刷题一半",
                tests: str = "408 | 第六章 | 80%") -> str:
    """按母版结构生成指定日期的日报。"""
    return (
        f"# 每日学习日报\n\n> {day.isoformat()} 收工\n\n"
        "### 今日成果\n今天推进了数据结构。\n\n"
        "### 明日三件事\n按优先级排列。\n\n" + tasks + "\n\n"
        "### 今日自测\n" + tests + "\n\n"
        "### 一句话点评\n保持节奏。\n"
    )


class CliTestCase(unittest.TestCase):
    """共用临时数据目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "reports").mkdir()


class TestLogTest(CliTestCase):
    """log-test：30 秒录一条自测。"""

    def test_writes_selftest_json(self):
        code, out, err = run_main([
            "log-test", "408", "数据结构第六章", "80%",
            "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 0, err)
        self.assertIn("已记录", out)
        self.assertIn("80%", out)

        path = self.root / "selftest.json"
        self.assertTrue(path.exists())
        records = load_records(path, SelfTest)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].subject, "408")
        self.assertEqual(records[0].section, "数据结构第六章")
        self.assertEqual(records[0].accuracy, 80.0)
        self.assertEqual(records[0].day, TODAY)  # 自动盖今天日期
        self.assertEqual(records[0].source, "manual")

    def test_appends_to_existing_file(self):
        for accuracy in ("70", "0.75"):
            code, _out, _err = run_main([
                "log-test", "math", "概率第三章", accuracy,
                "--data-dir", str(self.root),
            ])
            self.assertEqual(code, 0)
        records = load_records(self.root / "selftest.json", SelfTest)
        self.assertEqual([r.accuracy for r in records], [70.0, 75.0])

    def test_invalid_accuracy_exits_1(self):
        code, _out, err = run_main([
            "log-test", "408", "第六章", "良好",
            "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 1)
        self.assertIn("错误", err)
        # 失败不应留下半个文件
        self.assertFalse((self.root / "selftest.json").exists())


class TestReport(CliTestCase):
    """report：解析日报并打印摘要。"""

    def test_single_file_summary(self):
        md = self.root / "reports" / f"{TODAY.isoformat()}.md"
        md.write_text(report_text(TODAY), encoding="utf-8")
        # 同日的学习时长
        write_json(self.root / "log.json", [
            {"start": f"{TODAY.isoformat()}T09:00",
             "end": f"{TODAY.isoformat()}T11:30",
             "minutes": 150, "subject": "408", "note": ""},
        ])
        code, out, err = run_main([
            "report", str(md), "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 0, err)
        self.assertIn("三件事", out)
        self.assertIn("50%", out)  # 1 done / 2 reviewed
        self.assertIn("自测", out)
        self.assertIn("80%", out)
        self.assertIn("150.0 min", out)
        self.assertIn("408", out)

    def test_directory_of_reports(self):
        (self.root / "reports" / f"{TODAY.isoformat()}.md").write_text(
            report_text(TODAY), encoding="utf-8")
        yesterday = TODAY - timedelta(days=1)
        (self.root / "reports" / f"{yesterday.isoformat()}.md").write_text(
            report_text(yesterday, tasks="- [x] 单独完成",
                        tests="今日无自测"), encoding="utf-8")
        code, out, err = run_main([
            "report", str(self.root / "reports"), "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 0, err)
        self.assertIn("共解析 2 份日报", out)
        self.assertIn("100%", out)  # 昨天那条 1/1

    def test_broken_report_exits_1_with_line(self):
        md = self.root / "reports" / "bad.md"
        md.write_text(report_text(TODAY, tests="408 | 第六章 | 八十分"),
                      encoding="utf-8")
        code, _out, err = run_main([
            "report", str(md), "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 1)
        self.assertIn("行", err)
        self.assertIn("正确率", err)

    def test_missing_path_exits_1(self):
        code, _out, err = run_main([
            "report", str(self.root / "不存在.md"), "--data-dir", str(self.root),
        ])
        self.assertEqual(code, 1)
        self.assertIn("找不到", err)


class TestWeek(CliTestCase):
    """week：本周汇总全链路。"""

    def _fill_week_data(self) -> None:
        write_json(self.root / "log.json", [
            {"start": f"{TODAY.isoformat()}T09:00",
             "end": f"{TODAY.isoformat()}T11:00",
             "minutes": 120, "subject": "408", "note": ""},
            {"start": f"{TODAY.isoformat()}T14:00",
             "end": f"{TODAY.isoformat()}T15:00",
             "minutes": 60, "subject": "math", "note": ""},
            # 两周前的记录不应进本周表
            {"start": f"{(TODAY - timedelta(days=14)).isoformat()}T09:00",
             "end": f"{(TODAY - timedelta(days=14)).isoformat()}T11:00",
             "minutes": 120, "subject": "408", "note": ""},
        ])
        (self.root / "reports" / f"{TODAY.isoformat()}.md").write_text(
            report_text(TODAY), encoding="utf-8")
        write_json(self.root / "selftest.json", [
            {"subject": "408", "section": "第六章", "accuracy": 80,
             "date": TODAY.isoformat(), "source": "manual"},
        ])

    def test_full_week_table(self):
        self._fill_week_data()
        code, out, err = run_main(["week", "--data-dir", str(self.root)])
        self.assertEqual(code, 0, err)
        self.assertIn("本周汇总", out)
        self.assertIn("合计", out)
        self.assertIn("3h00m", out)          # 本周 180 min
        self.assertIn("科目分布", out)
        self.assertIn("408", out)
        self.assertIn("80%", out)            # 平均正确率
        # 两周前的 120 min 不应被算进合计（180+120=300 → 5h00m）
        self.assertNotIn("5h00m", out)

    def test_empty_data_dir_reports_no_data(self):
        code, out, err = run_main(["week", "--data-dir", str(self.root)])
        self.assertEqual(code, 0, err)
        self.assertIn("暂无数据", out)


class TestMisc(CliTestCase):
    """入口杂项。"""

    def test_no_args_prints_help(self):
        code, out, _err = run_main([])
        self.assertEqual(code, 0)
        self.assertIn("log-test", out)
        self.assertIn("week", out)

    def test_unknown_option_exits_with_code_2(self):
        with self.assertRaises(SystemExit) as ctx:
            run_main(["week", "--不存在的参数"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
