"""逃逸时间 + 平滑着色测试：心瓣包含点、连续性、视口与场。"""
import math
import unittest

from fractals.mandelbrot import (
    Viewport,
    escapes,
    julia_field,
    mandelbrot_field,
    smooth_escape,
)


def _integer_count(c: complex, max_iter: int = 256) -> int | None:
    """独立复刻整数逃逸计数（None = 集合内）。"""
    z = 0j
    for n in range(max_iter):
        z = z * z + c
        if abs(z) > 2.0:
            return n
    return None


class TestEscape(unittest.TestCase):
    def test_c_zero_never_escapes(self):
        """c=0：z ← z² 恒为 0，永远不逃逸（心瓣正中心）。"""
        self.assertFalse(escapes(0j))
        self.assertIsNone(smooth_escape(0j))

    def test_c_two_plus_i_escapes(self):
        """c=2+i：第一步 |z|=√5>2 即逃逸。"""
        self.assertTrue(escapes(2 + 1j))
        mu = smooth_escape(2 + 1j)
        self.assertIsNotNone(mu)
        self.assertGreater(mu, 0.0)
        self.assertLess(mu, 2.0)

    def test_cardioid_interior_point(self):
        """主心瓣内点 -0.5 收敛到不动点，256 次迭代内不逃逸。"""
        self.assertFalse(escapes(-0.5 + 0j, max_iter=256))
        self.assertIsNone(smooth_escape(-0.5 + 0j, max_iter=256))

    def test_smooth_value_brackets_integer_count(self):
        """平滑值落在 [n-0.5, n+1.6]：既贴近整数计数又带上小数修正。"""
        for c in (1 + 1j, 0.5 + 1.5j, 2 + 1j, 3 + 0j, -2.5 + 2.5j):
            with self.subTest(c=c):
                n = _integer_count(c)
                self.assertIsNotNone(n)
                mu = smooth_escape(c)
                self.assertIsNotNone(mu)
                self.assertGreater(mu, n - 0.5)
                self.assertLess(mu, n + 1.6)

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            smooth_escape(0j, max_iter=0)
        with self.assertRaises(ValueError):
            smooth_escape(1j, escape_radius=1.0)


class TestSmoothContinuity(unittest.TestCase):
    def test_squaring_identity(self):
        """连续性的代数内核：μ(n, M) == μ(n+1, M²)，差 1 被 log₂ 抵消。"""
        log2 = math.log(2.0)
        for n in (0, 1, 5, 10):
            for m in (2.5, 4.0, 6.0):
                v1 = n + 1.0 - math.log(math.log(m)) / log2
                v2 = (n + 1) + 1.0 - math.log(math.log(m * m)) / log2
                self.assertAlmostEqual(v1, v2, places=12,
                                       msg=f"n={n}, M={m}")

    def test_jump_suppressed_at_escape_boundary(self):
        """实轴上逃逸计数跳 1 处，平滑值台阶被压到 0.3 以下。"""
        eps = 1e-7

        # 1) 在 [0.40, 0.46] 扫描找到第一个计数变化点
        prev = None
        lo = hi = None
        n_lo = n_hi = None
        step = 1e-4
        for i in range(601):
            x = 0.40 + i * step
            n = _integer_count(complex(x, 0))
            if prev is not None and n != prev:
                lo, hi, n_lo, n_hi = x - step, x, prev, n
                break
            prev = n
        self.assertIsNotNone(lo, "未找到逃逸计数边界")

        # 2) 二分逼近边界
        for _ in range(60):
            mid = (lo + hi) / 2
            if _integer_count(complex(mid, 0)) == n_lo:
                lo = mid
            else:
                hi = mid
        c = complex((lo + hi) / 2, 0)

        # 3) 边界两侧 ±1e-7 处测量
        n_a = _integer_count(c - eps)
        n_b = _integer_count(c + eps)
        mu_a = smooth_escape(c - eps)
        mu_b = smooth_escape(c + eps)
        self.assertIsNotNone(n_a)
        self.assertIsNotNone(n_b)
        self.assertEqual(abs(n_a - n_b), 1)          # 整数着色：跳 1
        self.assertLess(abs(mu_a - mu_b), 0.3)      # 平滑着色：台阶 < 0.3

    def test_correction_term_monotone_in_modulus(self):
        """同一逃逸代数下，末值模越大 μ 越小（颜色随 |z| 连续变化）。"""
        log2 = math.log(2.0)
        values = [5 + 1.0 - math.log(math.log(m)) / log2
                  for m in (2.1, 3.0, 4.5, 6.0)]
        for a, b in zip(values, values[1:]):
            self.assertGreater(a, b)


class TestViewport(unittest.TestCase):
    def test_centered_defaults_square(self):
        vp = Viewport.centered(0.0, 0.0, 2.0)
        self.assertEqual(vp, Viewport(-2.0, 2.0, -2.0, 2.0))
        self.assertAlmostEqual(vp.width, 4.0)
        self.assertAlmostEqual(vp.height, 4.0)

    def test_point_mapping(self):
        vp = Viewport(-2.0, 2.0, -2.0, 2.0)
        top_left = vp.point(0, 0, 100, 100)
        self.assertAlmostEqual(top_left.real, -1.98)
        self.assertAlmostEqual(top_left.imag, 1.98)   # row 0 = 顶部 = 最大虚部
        bottom_right = vp.point(99, 99, 100, 100)
        self.assertAlmostEqual(bottom_right.real, 1.98)
        self.assertAlmostEqual(bottom_right.imag, -1.98)

    def test_point_out_of_range_raises(self):
        vp = Viewport(-1.0, 1.0, -1.0, 1.0)
        with self.assertRaises(ValueError):
            vp.point(10, 0, 10, 10)

    def test_invalid_viewport_raises(self):
        with self.assertRaises(ValueError):
            Viewport(1.0, 1.0, -1.0, 1.0)
        with self.assertRaises(ValueError):
            Viewport.centered(0.0, 0.0, 0.0)

    def test_contains(self):
        vp = Viewport(-1.0, 1.0, -1.0, 1.0)
        self.assertTrue(vp.contains(0j))
        self.assertFalse(vp.contains(2j))


class TestFields(unittest.TestCase):
    def test_mandelbrot_field_dimensions(self):
        field = mandelbrot_field(5, 3, max_iter=50)
        self.assertEqual(len(field), 3)
        for row in field:
            self.assertEqual(len(row), 5)

    def test_field_invalid_size_raises(self):
        with self.assertRaises(ValueError):
            mandelbrot_field(0, 10)

    def test_julia_c_parameter_changes_field(self):
        """c 是 Julia 集的『遗传参数』：换一个 c，场必然不同。"""
        a = julia_field(16, 16, 0j, max_iter=50)
        b = julia_field(16, 16, 0.5j, max_iter=50)
        self.assertNotEqual(a, b)

    def test_julia_disk_inside(self):
        """c=0 时 Julia 集是单位圆盘：原点不逃逸，远处逃逸。"""
        self.assertIsNone(smooth_escape(0j, max_iter=50, z0=0j))
        self.assertTrue(escapes(0j, max_iter=50, z0=1.5 + 0j))


if __name__ == "__main__":
    unittest.main()
