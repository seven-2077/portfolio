"""ascii_anim.py 单元测试：字符画渲染、演示模式帧数、退出轮询。"""

from __future__ import annotations

import io
import unittest

from pendulum.ode import DEFAULT
from viz import ascii_anim as aa


class TestRender(unittest.TestCase):
    def test_grid_dimensions(self):
        rows = aa.render((1.0, 0.5, -1.0, -0.5), width=41, height=21)
        self.assertEqual(len(rows), 21)
        for row in rows:
            self.assertEqual(len(row), 41)

    def test_contains_pivot_rods_and_bobs(self):
        rows = aa.render(aa.DEFAULT_STATE)
        canvas = "\n".join(rows)
        self.assertIn(aa.CHAR_PIVOT, canvas)   # 支点 +
        self.assertEqual(canvas.count(aa.CHAR_BOB), 2)  # 两个摆球
        self.assertIn(aa.CHAR_ROD, canvas)     # 摆杆采样点

    def test_pivot_placed_at_mapped_cell(self):
        """支点 '+' 落在 (0,0) 的映射位置（视野中央）。"""
        rows = aa.render((0.5, 0.0, -0.5, 0.0), width=61, height=31)
        row, col = aa._cell(0.0, 0.0, 61, 31, r=DEFAULT.l1 + DEFAULT.l2)
        self.assertEqual(rows[row][col], aa.CHAR_PIVOT)

    def test_trail_drawn_when_provided(self):
        rows = aa.render(aa.DEFAULT_STATE, trail=[(0.5, -1.0), (-0.5, -1.5)])
        canvas = "\n".join(rows)
        self.assertIn(aa.CHAR_TRAIL, canvas)


class TestAnimation(unittest.TestCase):
    def test_demo_mode_renders_sampled_frames(self):
        """非交互模式：固定帧数、抽样打印、不抛异常。"""
        out = io.StringIO()
        shown = aa.run_animation(frames=3, sleep_s=0.0, interactive=False, out=out)
        text = out.getvalue()
        self.assertEqual(shown, 3)                     # 3 帧全部命中抽样点
        self.assertIn("frame 1/3", text)
        self.assertIn("frame 3/3", text)
        self.assertNotIn("\x1b[2J", text)              # 演示模式不清屏
        self.assertIn(aa.CHAR_BOB, text)

    def test_quit_poll_stops_early(self):
        """注入退出条件（msvcrt 轮询的测试替身）→ 提前收场。"""
        out = io.StringIO()
        calls = {"n": 0}

        def quit_after_two():
            calls["n"] += 1
            return calls["n"] >= 2

        shown = aa.run_animation(frames=100, sleep_s=0.0, interactive=False,
                                 quit_poll=quit_after_two, out=out)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(shown, 1)   # 只打印了第 0 帧就退出
        self.assertLess(shown, 100)

    def test_hud_reports_energy(self):
        out = io.StringIO()
        aa.run_animation(frames=3, sleep_s=0.0, interactive=False, out=out)
        self.assertIn("E =", out.getvalue())
        self.assertIn("J", out.getvalue())

    def test_custom_params_render_without_error(self):
        from pendulum.ode import Params
        p = Params(m1=2.0, m2=1.5, l1=1.2, l2=0.8)
        rows = aa.render((1.2, 0.3, -0.7, -0.2), params=p, width=51, height=25)
        self.assertEqual(len(rows), 25)
        self.assertIn(aa.CHAR_BOB, "\n".join(rows))


if __name__ == "__main__":
    unittest.main()
