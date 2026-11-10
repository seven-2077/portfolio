"""ode.py 单元测试：方程结构、平衡点、单摆周期标定、与教科书闭式对照。"""

from __future__ import annotations

import math
import unittest

from pendulum import integrate, ode
from pendulum.ode import DEFAULT, Params


class TestDerivativeStructure(unittest.TestCase):
    """右端函数的基本契约。"""

    def test_returns_four_floats(self):
        d = ode.derivatives((0.3, 0.5, -0.2, -0.7))
        self.assertEqual(len(d), 4)
        for v in d:
            self.assertIsInstance(v, float)

    def test_downward_equilibrium_is_stationary(self):
        """双杆下垂、静止 → 重力力矩为零，所有导数为 0。"""
        for v in ode.derivatives((0.0, 0.0, 0.0, 0.0)):
            self.assertAlmostEqual(v, 0.0, places=12)

    def test_angle_derivative_equals_omega(self):
        """一阶化的结构约束：dθ/dt = ω。"""
        d = ode.derivatives((0.3, 0.5, -0.2, -0.7))
        self.assertAlmostEqual(d[0], 0.5, places=12)
        self.assertAlmostEqual(d[2], -0.7, places=12)

    def test_params_are_immutable(self):
        """Params 不可变，多处共享也不会互相污染。"""
        with self.assertRaises(Exception):
            DEFAULT.g = 10.0  # type: ignore[misc]


class TestSinglePendulumPeriod(unittest.TestCase):
    """单摆小角度周期 vs 解析解 2π√(l/g) —— 标定积分器精度。"""

    L, G, TH0 = 1.0, 9.81, 0.01

    def test_small_angle_period_matches_analytic(self):
        p = ode.Params(l1=self.L, g=self.G)

        def e_fn(s):
            return 0.5 * p.m1 * (p.l1 * s[1]) ** 2 + p.m1 * p.g * p.l1 * (1.0 - math.cos(s[0]))

        rk = integrate.RK4(deriv=ode.single_pendulum_derivatives, params=p,
                           dt=5e-4, energy_fn=e_fn)
        t_exact = 2.0 * math.pi * math.sqrt(self.L / self.G)
        snaps = rk.integrate((self.TH0, 0.0), 0.0, 3.0 * t_exact + 0.1)

        # 找 θ 上穿 0（ω>0）的时刻，相邻两次之差 = 实测周期
        crossings = []
        for a, b in zip(snaps, snaps[1:]):
            if a.state[0] < 0.0 <= b.state[0] and a.state[1] > 0.0:
                f = -a.state[0] / (b.state[0] - a.state[0])
                crossings.append(a.t + f * (b.t - a.t))
        self.assertGreaterEqual(len(crossings), 3)

        for t1, t2 in zip(crossings, crossings[1:]):
            period = t2 - t1
            rel_err = abs(period - t_exact) / t_exact
            # 理论非线性修正 θ0²/16 ≈ 6.25e-6，阈值留 10 倍余量
            self.assertLess(rel_err, 1e-4,
                            f"周期 {period} vs 解析 {t_exact}，相对误差 {rel_err}")


class TestAgainstTextbookClosedForm(unittest.TestCase):
    """与 Wikipedia/教科书的双摆闭式解对照（独立推导路径的交叉验证）。"""

    @staticmethod
    def _wiki(state, p: Params):
        th1, w1, th2, w2 = state
        m1, m2, l1, l2, g = p.m1, p.m2, p.l1, p.l2, p.g
        d = th1 - th2
        common = 2.0 * m1 + m2 - m2 * math.cos(2.0 * d)
        a1 = (
            -g * (2.0 * m1 + m2) * math.sin(th1)
            - m2 * g * math.sin(th1 - 2.0 * th2)
            - 2.0 * math.sin(d) * m2 * (w2 * w2 * l2 + w1 * w1 * l1 * math.cos(d))
        ) / (l1 * common)
        a2 = (
            2.0 * math.sin(d)
            * (w1 * w1 * l1 * (m1 + m2) + g * (m1 + m2) * math.cos(th1)
               + w2 * w2 * l2 * m2 * math.cos(d))
        ) / (l2 * common)
        return a1, a2

    def test_matches_closed_form_on_varied_states(self):
        p = Params(m1=1.3, m2=0.7, l1=1.1, l2=0.9, g=9.81)  # 非对称参数，防巧合
        states = [
            (0.6, 1.4, -0.5, -0.9),
            (2.5, -0.8, 1.1, 2.0),
            (0.01, 0.02, -0.01, 0.03),
            (-2.9, 3.5, 2.2, -4.0),
        ]
        for s in states:
            got = ode.derivatives(s, p)
            a1, a2 = self._wiki(s, p)
            self.assertAlmostEqual(got[1], a1, places=9, msg=f"state={s}")
            self.assertAlmostEqual(got[3], a2, places=9, msg=f"state={s}")

    def test_mass_matrix_determinant_always_positive(self):
        """det = m2 l1² l2² (m1 + m2 sin²δ) > 0 —— 不会出现除零。"""
        for s in [(0.0, 0.0, 0.0, 0.0), (2.0, 1.0, -2.0, -1.0), (0.5, 9.0, 0.5, -9.0)]:
            d = ode.derivatives(s)  # 不抛异常即通过
            self.assertTrue(all(math.isfinite(v) for v in d))


if __name__ == "__main__":
    unittest.main()
