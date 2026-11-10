"""demo 测试：预录脚本合法性 + 无头巡游实跑（烟雾测试）。"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo import SIM_FPS, build_script, main

VALID_ACTIONS = {"forward", "back", "strafe_l", "strafe_r",
                 "turn_l", "turn_r", "shoot", "toggle_map", "quit"}


class TestBuildScript(unittest.TestCase):
    def test_entries_well_formed(self):
        script = build_script()
        self.assertGreater(len(script), 20)
        for actions, frames in script:
            self.assertTrue(actions, "每段都该带动作")
            self.assertTrue(actions <= VALID_ACTIONS,
                            f"未知动作 {actions - VALID_ACTIONS}")
            self.assertGreater(frames, 0)

    def test_script_covers_tour(self):
        union: set = set()
        total = 0
        for actions, frames in build_script():
            union |= actions
            total += frames
        self.assertIn("forward", union)          # 确实在走图
        self.assertIn("shoot", union)            # 确实开了枪
        self.assertIn("turn_l", union)           # 确实转过头
        self.assertGreater(total, 500)           # 覆盖足够长的路程
        self.assertEqual(SIM_FPS, 30.0)          # 巡游按 30Hz 步进


class TestHeadlessDemo(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue()

    def test_demo_runs_and_reports(self):
        code, text = self._run(["--demo", "--no-record", "--frames", "10",
                                "--map", "crypt"])
        self.assertEqual(code, 0)
        self.assertIn("自动巡游", text)
        self.assertIn("渲染帧数", text)
        self.assertIn("实测帧率", text)
        self.assertIn("结局", text)

    def test_demo_on_random_map(self):
        code, text = self._run(["--demo", "--no-record", "--frames", "10",
                                "--map", "random", "--seed", "5"])
        self.assertEqual(code, 0)
        self.assertIn("random", text)

    def test_tiny_window_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(["--demo", "--width", "10", "--height", "4"])


if __name__ == "__main__":
    unittest.main()
