"""海龟解释器测试：几何动作、分支栈平衡、坐标归一化。"""
import unittest

from fractals.turtle import (
    Segment,
    TurtleError,
    bounding_box,
    interpret,
    normalize,
)


class _CoordMixin:
    """坐标比较统一走 almostEqual——cos(90°) 在浮点下是 6.1e-17 而非 0。"""

    def assertSeg(self, seg: Segment, x1, y1, x2, y2, places=9):
        for got, want in zip((seg.x1, seg.y1, seg.x2, seg.y2),
                             (x1, y1, x2, y2)):
            self.assertAlmostEqual(got, want, places=places)

    def assertBox(self, segs, x_min, y_min, x_max, y_max, places=9):
        for got, want in zip(bounding_box(segs), (x_min, y_min, x_max, y_max)):
            self.assertAlmostEqual(got, want, places=places)


class TestInterpret(_CoordMixin, unittest.TestCase):
    def test_forward_default_heading_is_up(self):
        segs = interpret("F")
        self.assertEqual(len(segs), 1)
        self.assertSeg(segs[0], 0.0, 0.0, 0.0, 1.0)

    def test_plus_turns_left(self):
        """'+' 左转（逆时针）：heading 90° 再 +90° 指向西（-x）。"""
        segs = interpret("F+F", angle=90)
        self.assertEqual(len(segs), 2)
        self.assertSeg(segs[1], 0.0, 1.0, -1.0, 1.0)

    def test_minus_turns_right(self):
        segs = interpret("F-F", angle=90)
        self.assertSeg(segs[1], 0.0, 1.0, 1.0, 1.0)

    def test_push_pop_restores_position_and_heading(self):
        """[] 分支：弹栈后位置与朝向完全恢复，主干继续向上。"""
        segs = interpret("F[+F]F")
        self.assertEqual(len(segs), 3)
        self.assertSeg(segs[0], 0.0, 0.0, 0.0, 1.0)    # 主干
        self.assertSeg(segs[1], 0.0, 1.0, -1.0, 1.0)   # 侧枝
        self.assertSeg(segs[2], 0.0, 1.0, 0.0, 2.0)    # 恢复后继续

    def test_nested_branches(self):
        segs = interpret("F[F[F]F]F")
        self.assertEqual(len(segs), 5)

    def test_move_pen_up_draws_nothing(self):
        """f 移笔不画线：起点被抬高一个步长，只有随后的 F 留下线段。"""
        segs = interpret("fF")
        self.assertEqual(len(segs), 1)
        self.assertSeg(segs[0], 0.0, 1.0, 0.0, 2.0)

    def test_aux_symbols_silently_ignored(self):
        self.assertEqual(interpret("FX+Y"), interpret("F+"))

    def test_step_scales_length(self):
        segs = interpret("F", step=2.5)
        self.assertAlmostEqual(segs[0].length, 2.5)

    def test_underflow_raises(self):
        with self.assertRaises(TurtleError):
            interpret("]")

    def test_unclosed_bracket_raises(self):
        with self.assertRaises(TurtleError):
            interpret("[F")

    def test_extra_closing_raises_inside_nesting(self):
        with self.assertRaises(TurtleError):
            interpret("F[F]]")


class TestBoundingBox(_CoordMixin, unittest.TestCase):
    def test_empty_returns_zeros(self):
        self.assertEqual(bounding_box([]), (0.0, 0.0, 0.0, 0.0))

    def test_simple_box(self):
        segs = interpret("F+F", angle=90)  # (0,0)-(0,1), (0,1)-(-1,1)
        self.assertBox(segs, -1.0, 0.0, 0.0, 1.0)


class TestNormalize(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(normalize([]), [])

    def test_margin_validation(self):
        with self.assertRaises(ValueError):
            normalize([Segment(0, 0, 1, 1)], margin=0.6)

    def test_degenerate_vertical_line_fills_height(self):
        """纯纵向线段（span_x=0）也必须按高度填满画框。"""
        out = normalize([Segment(0, 0, 0, 0.1)], margin=0.05)
        s = out[0]
        self.assertAlmostEqual(s.y1, 0.05)
        self.assertAlmostEqual(s.y2, 0.95)
        self.assertAlmostEqual(s.x1, 0.5)

    def test_degenerate_horizontal_line_fills_width(self):
        out = normalize([Segment(0, 0, 0.1, 0)], margin=0.05)
        s = out[0]
        self.assertAlmostEqual(s.x1, 0.05)
        self.assertAlmostEqual(s.x2, 0.95)
        self.assertAlmostEqual(s.y1, 0.5)

    def test_aspect_ratio_preserved(self):
        """4:1 图形归一化后宽高比不变，且落在边距内。"""
        out = normalize([Segment(0, 0, 4, 1)], margin=0.05)
        x_min, y_min, x_max, y_max = bounding_box(out)
        w, h = x_max - x_min, y_max - y_min
        self.assertAlmostEqual(w / h, 4.0, places=9)
        for v in (x_min, y_min, x_max, y_max):
            self.assertGreaterEqual(v, 0.05 - 1e-12)
            self.assertLessEqual(v, 0.95 + 1e-12)

    def test_centered(self):
        out = normalize([Segment(0, 0, 2, 1)], margin=0.0)
        x_min, y_min, x_max, y_max = bounding_box(out)
        self.assertAlmostEqual((x_min + x_max) / 2, 0.5)
        self.assertAlmostEqual((y_min + y_max) / 2, 0.5)


if __name__ == "__main__":
    unittest.main()
