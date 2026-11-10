"""预置植物测试：数量、元数据、Koch 长度 (4/3)^n 增长、龙曲线段数翻倍。"""
import unittest

from fractals.plants import PRESETS
from fractals.turtle import interpret


class TestPresets(unittest.TestCase):
    def test_at_least_four_presets(self):
        self.assertGreaterEqual(len(PRESETS), 4)

    def test_required_presets_present(self):
        for name in ("fern", "koch_snowflake", "dragon"):
            self.assertIn(name, PRESETS)

    def test_preset_metadata(self):
        """每个预置都带可用的公理、规则、推荐角度与迭代数。"""
        for name, p in PRESETS.items():
            with self.subTest(preset=name):
                self.assertTrue(p.axiom)
                self.assertTrue(p.rules)
                self.assertGreater(p.angle, 0)
                self.assertGreaterEqual(p.iterations, 1)
                self.assertTrue(p.description)

    def test_fern_first_iteration_from_preset(self):
        p = PRESETS["fern"]
        code = p.lsystem().iterate(1)
        self.assertEqual(code, "F+[[X]-X]-F[-FX]+X")


class TestKoch(unittest.TestCase):
    def test_curve_length_grows_4_3_pow_n(self):
        """单边 Koch：第 n 代把边长缩为 3^-n、段数 4^n，总长 (4/3)^n。"""
        p = PRESETS["koch_curve"]
        ls = p.lsystem()
        for n in range(6):
            code = ls.iterate(n)
            segs = interpret(code, angle=p.angle, step=3.0 ** (-n))
            total = sum(s.length for s in segs)
            self.assertAlmostEqual(total, (4.0 / 3.0) ** n, places=9,
                                   msg=f"n={n}")

    def test_snowflake_segment_count(self):
        """雪花从等边三角形（3 段）出发，每代段数 ×4。"""
        p = PRESETS["koch_snowflake"]
        ls = p.lsystem()
        for n in range(5):
            segs = interpret(ls.iterate(n), angle=p.angle)
            self.assertEqual(len(segs), 3 * 4 ** n, f"n={n}")

    def test_snowflake_raw_grows_3x_per_iteration(self):
        """步长固定为 1 时原始坐标每代恰 ×3 生长（渲染前会归一化抵消）。"""
        from fractals.turtle import bounding_box

        p = PRESETS["koch_snowflake"]
        ls = p.lsystem()
        spans = []
        for n in (2, 3, 4):
            segs = interpret(ls.iterate(n), angle=p.angle)
            x_min, _, x_max, _ = bounding_box(segs)
            spans.append(x_max - x_min)
        for a, b in zip(spans, spans[1:]):
            self.assertAlmostEqual(b / a, 3.0, places=6)

    def test_snowflake_normalized_shape_converges(self):
        """归一化后各代落在单位框内，且宽高比已收敛（形状稳定）。"""
        from fractals.turtle import bounding_box, normalize

        p = PRESETS["koch_snowflake"]
        ls = p.lsystem()
        ratios = []
        for n in (3, 4, 5):
            segs = normalize(interpret(ls.iterate(n), angle=p.angle),
                             margin=0.0)
            x_min, y_min, x_max, y_max = bounding_box(segs)
            self.assertGreaterEqual(x_min, -1e-9)
            self.assertGreaterEqual(y_min, -1e-9)
            self.assertLessEqual(x_max, 1.0 + 1e-9)
            self.assertLessEqual(y_max, 1.0 + 1e-9)
            ratios.append((x_max - x_min) / (y_max - y_min))
        for a, b in zip(ratios, ratios[1:]):
            self.assertAlmostEqual(a, b, places=6)


class TestDragon(unittest.TestCase):
    def test_segment_count_doubles_each_iteration(self):
        """龙曲线：F 段数恰为 2^n（n=0 时公理 FX 只有一个 F）。"""
        p = PRESETS["dragon"]
        ls = p.lsystem()
        for n in range(7):
            segs = interpret(ls.iterate(n), angle=p.angle)
            self.assertEqual(len(segs), 2 ** n, f"n={n}")

    def test_dragon_is_bracket_free(self):
        """龙曲线无分支：解释时永不触碰分支栈。"""
        p = PRESETS["dragon"]
        code = p.lsystem().iterate(6)
        self.assertNotIn("[", code)
        self.assertNotIn("]", code)


if __name__ == "__main__":
    unittest.main()
