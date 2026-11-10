"""开普勒方程求解测试：收敛性、圆轨道退化、发散保护。"""

import math
import unittest

from orbit.kepler import KeplerError, orbital_radius, solve_kepler, true_anomaly

# 椭圆轨道偏心率取样：地球 0.017、火星 0.093、水星 0.206、再加两个高偏心率
_ECCS = (0.0, 0.01671123, 0.09339410, 0.20563593, 0.5, 0.9)


class TestKeplerConvergence(unittest.TestCase):
    def test_residual_grid(self):
        """M 网格 × 多个偏心率：残差 |E - e·sinE - M| < 1e-10。"""
        for e in _ECCS:
            for k in range(-24, 25):
                M = math.pi * k / 24.0
                Mn = math.remainder(M, 2.0 * math.pi)
                E = solve_kepler(M, e)
                resid = abs(E - e * math.sin(E) - Mn)
                self.assertLess(resid, 1e-10, f"e={e}, M={M}, 残差={resid}")

    def test_converges_to_machine_precision(self):
        """默认 tol=1e-12：残差达到 1e-12 量级。"""
        E = solve_kepler(1.234, 0.20563593)
        self.assertLess(abs(E - 0.20563593 * math.sin(E) - 1.234), 5e-12)

    def test_oracle_against_plain_bisection(self):
        """与独立的纯二分法参考实现对照（e=0.8 高偏心率）。"""
        e, M = 0.8, 0.7

        def f(x: float) -> float:
            return x - e * math.sin(x) - M

        lo, hi = M - e, M + e
        for _ in range(200):  # 独立二分到 ~1e-15
            mid = 0.5 * (lo + hi)
            if f(mid) > 0:
                hi = mid
            else:
                lo = mid
        ref = 0.5 * (lo + hi)
        self.assertAlmostEqual(solve_kepler(M, e), ref, places=11)


class TestCircularOrbit(unittest.TestCase):
    def test_e_zero_gives_e_equals_m(self):
        """e=0 时开普勒方程退化为 E = M，必须精确成立。"""
        for k in range(0, 36):
            M = 2.0 * math.pi * k / 36.0
            E = solve_kepler(M, 0.0)
            self.assertAlmostEqual(E, math.remainder(M, 2.0 * math.pi),
                                   places=15)

    def test_e_zero_with_no_newton_iterations(self):
        """e=0 且 max_iter=0：残差检查直接放行，仍返回 M。"""
        self.assertEqual(solve_kepler(0.5, 0.0, max_iter=0), 0.5)


class TestGuardRails(unittest.TestCase):
    def test_iteration_limit_falls_back_to_bisection(self):
        """牛顿迭代被禁用（max_iter=0）时，二分兜底仍给出正确根。"""
        M, e = -2.0, 0.5
        E = solve_kepler(M, e, max_iter=0)
        resid = abs(E - e * math.sin(E) - math.remainder(M, 2 * math.pi))
        self.assertLess(resid, 1e-10)

    def test_iteration_bound_respected(self):
        """正常情形下牛顿迭代远在上限内收敛（本题根数 e<0.21）。"""
        for k in range(12):
            M = -math.pi + 2 * math.pi * k / 12
            # 不抛异常即说明在 max_iter 内收敛
            solve_kepler(M, 0.20563593, max_iter=30)

    def test_invalid_eccentricity_raises(self):
        for bad in (1.0, 1.5, -0.1):
            with self.assertRaises(ValueError):
                solve_kepler(0.0, bad)

    def test_kepler_error_type_exists(self):
        self.assertTrue(issubclass(KeplerError, RuntimeError))


class TestGeometryHelpers(unittest.TestCase):
    def test_perihelion_geometry(self):
        """E=0 → 真近点角 0、r = a(1-e)（近日点）。"""
        a, e = 0.38709927, 0.20563593
        self.assertEqual(true_anomaly(0.0, e), 0.0)
        self.assertAlmostEqual(orbital_radius(a, 0.0, e), a * (1 - e), places=12)

    def test_aphelion_geometry(self):
        """E=π → 真近点角 π、r = a(1+e)（远日点）。"""
        a, e = 0.38709927, 0.20563593
        self.assertAlmostEqual(abs(true_anomaly(math.pi, e)), math.pi,
                               places=12)
        self.assertAlmostEqual(orbital_radius(a, math.pi, e), a * (1 + e),
                               places=12)

    def test_true_anomaly_quadrant(self):
        """0 < E < π 时真近点角为正（轨道前半段）。"""
        self.assertGreater(true_anomaly(1.0, 0.2), 0.0)


if __name__ == "__main__":
    unittest.main()
