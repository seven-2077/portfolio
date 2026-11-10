"""energy.py 单元测试：边界情形、非负性、守恒与漂移上限。"""

from __future__ import annotations

import math
import unittest

from pendulum import energy, integrate, ode


class TestBoundaryCases(unittest.TestCase):
    def test_rest_at_bottom_is_exactly_zero(self):
        """静止 + 双杆下垂 → T = V = E 全为 0（势能零点约定）。"""
        state = (0.0, 0.0, 0.0, 0.0)
        self.assertEqual(energy.kinetic(state), 0.0)
        self.assertEqual(energy.potential(state), 0.0)
        self.assertEqual(energy.total(state), 0.0)

    def test_kinetic_zero_whenever_at_rest(self):
        """只要不转，无论摆到哪，动能都是 0。"""
        for th in (0.5, 1.5, -2.8, 3.0):
            self.assertEqual(energy.kinetic((th, 0.0, -th, 0.0)), 0.0)

    def test_potential_nonnegative_everywhere(self):
        """V = mg l (1-cosθ) ≥ 0，网格扫描不得为负。"""
        for i in range(-6, 7):
            for j in range(-6, 7):
                s = (i * 0.5, 0.0, j * 0.5, 0.0)
                self.assertGreaterEqual(energy.potential(s), -1e-12, msg=f"state={s}")

    def test_kinetic_nonnegative_even_with_counter_rotation(self):
        """动能是正定二次型：交叉项不会把总动能拉成负数。"""
        for w1 in (-3.0, -0.5, 0.0, 1.0, 4.0):
            for w2 in (-4.0, -1.0, 0.0, 2.0, 5.0):
                s = (1.0, w1, -1.0, w2)
                self.assertGreaterEqual(energy.kinetic(s), -1e-12, msg=f"w=({w1},{w2})")

    def test_potential_increases_with_height(self):
        """摆得越高势能越大：θ=π/2 应高于 θ=π/4。"""
        lo = energy.potential((math.pi / 4, 0.0, 0.0, 0.0))
        hi = energy.potential((math.pi / 2, 0.0, 0.0, 0.0))
        self.assertGreater(hi, lo)

    def test_drift_series_uses_first_frame_as_reference(self):
        self.assertEqual(energy.drift([10.0, 10.5, 9.5]), [0.0, 0.5, -0.5])
        self.assertEqual(energy.drift([]), [])


class TestConservation(unittest.TestCase):
    """能量守恒 = 数值质量体检。"""

    def test_single_pendulum_energy_tight_bound(self):
        """单摆：RK4 dt=5e-4 跑 3 个周期，相对漂移 < 1e-8。"""
        p = ode.Params(l1=1.0, g=9.81)

        def e_fn(s):
            return 0.5 * p.m1 * (p.l1 * s[1]) ** 2 + p.m1 * p.g * p.l1 * (1.0 - math.cos(s[0]))

        rk = integrate.RK4(deriv=ode.single_pendulum_derivatives, params=p,
                           dt=5e-4, energy_fn=e_fn)
        snaps = rk.integrate((0.5, 0.0), 0.0, 6.0)
        e0 = snaps[0].energy
        rel = max(abs(s.energy - e0) for s in snaps) / e0
        self.assertLess(rel, 1e-8, f"相对漂移 {rel}")

    def test_double_pendulum_drift_within_bound(self):
        """双摆混沌轨道（demo 设置）：dt=1e-3 跑 10s，相对漂移 < 1e-6。

        实测 ~5e-9，阈值留 200 倍余量；一旦方程推导错，这里会直接爆掉。
        """
        base = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)
        snaps = integrate.RK4(dt=1e-3).integrate(base, 0.0, 10.0)
        e0 = snaps[0].energy
        drift = max(abs(s.energy - e0) for s in snaps)
        rel = drift / e0
        self.assertLess(rel, 1e-6, f"max|ΔE|={drift:.3e} J，相对 {rel:.3e}")

    def test_energy_drift_bounded_under_long_run(self):
        """长跑 20s（dt=1e-3）漂移仍受控：绝对值 < 1e-4 J。"""
        base = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)
        snaps = integrate.RK4(dt=1e-3).integrate(base, 0.0, 20.0)
        e0 = snaps[0].energy
        drift = max(abs(s.energy - e0) for s in snaps)
        self.assertLess(drift, 1e-4, f"max|ΔE|={drift:.3e} J")


if __name__ == "__main__":
    unittest.main()
