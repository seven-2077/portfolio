"""integrate.py 单元测试：RK4 精度、四阶收敛、快照完整性、扩展位接口。"""

from __future__ import annotations

import math
import unittest

from pendulum import energy, integrate
from pendulum.integrate import RK4, Snapshot
from pendulum.ode import DEFAULT


class TestRK4Accuracy(unittest.TestCase):
    def test_exponential_decay_against_analytic(self):
        """y' = -y, y(1) = e⁻¹；RK4 dt=0.01 应到 1e-8 精度。"""
        rk = RK4(deriv=lambda s, p: (-s[0],), dt=0.01, energy_fn=lambda s: 0.0)
        snaps = rk.integrate((1.0,), 0.0, 1.0)
        err = abs(snaps[-1].state[0] - math.exp(-1.0))
        self.assertLess(err, 1e-8)

    def test_convergence_order_is_fourth(self):
        """步长减半，误差应约 1/16：d1/d2 ∈ (10, 22)。"""
        base = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)

        def final(dt):
            return RK4(dt=dt).integrate(base, 0.0, 2.0)[-1].state

        s1, s2, s4 = final(0.02), final(0.01), final(0.005)
        d1 = math.dist(s1, s2)   # 粗 vs 中
        d2 = math.dist(s2, s4)   # 中 vs 细
        ratio = d1 / d2
        self.assertGreater(ratio, 10.0, f"ratio={ratio:.2f}，远低于 16 说明阶数不足")
        self.assertLess(ratio, 22.0, f"ratio={ratio:.2f}，超过 16 太多说明步长未进渐近区")


class TestSnapshots(unittest.TestCase):
    def test_snapshot_count_and_time_grid(self):
        rk = RK4(dt=0.01)
        snaps = rk.integrate((0.1, 0.0, 0.1, 0.0), 0.0, 1.0)
        self.assertEqual(len(snaps), 101)
        self.assertEqual(snaps[0].t, 0.0)
        self.assertAlmostEqual(snaps[-1].t, 1.0, places=12)
        ts = [s.t for s in snaps]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(all(isinstance(s, Snapshot) for s in snaps))

    def test_snapshot_energy_matches_energy_module(self):
        rk = RK4(dt=0.005)  # 默认 energy_fn = 双摆总能量
        snaps = rk.integrate((2.0, 0.5, -1.0, -0.3), 0.0, 0.5)
        for s in snaps:
            self.assertAlmostEqual(s.energy, energy.total(s.state, DEFAULT), places=12)

    def test_energy_recorded_at_every_step(self):
        """每步快照都带能量且有限（不为 NaN/inf）。"""
        rk = RK4(dt=0.01, energy_fn=lambda s: 42.0)
        snaps = rk.integrate((0.2, 0.0, -0.2, 0.0), 0.0, 1.0)
        self.assertEqual(len(snaps), 101)
        self.assertTrue(all(s.energy == 42.0 for s in snaps))


class TestExtensionInterface(unittest.TestCase):
    def test_adaptive_hook_reserved(self):
        """suggest_dt 是变步长扩展位：当前未实现应显式抛 NotImplementedError。"""
        rk = RK4(dt=0.01)
        with self.assertRaises(NotImplementedError):
            rk.suggest_dt((0.1, 0.0, 0.1, 0.0), 0.0)

    def test_base_class_step_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            integrate.Integrator().step((0.0,), 0.0, 0.1)

    def test_invalid_dt_rejected(self):
        with self.assertRaises(ValueError):
            RK4(dt=0.0)

    def test_step_accepts_per_call_dt(self):
        """step(state, t, dt) 支持单次覆盖步长（为变步长预留的入口）。"""
        rk = RK4(deriv=lambda s, p: (1.0,), dt=0.1, energy_fn=lambda s: 0.0)
        out = rk.step((0.0,), 0.0, 0.5)
        self.assertAlmostEqual(out[0], 0.5, places=12)


if __name__ == "__main__":
    unittest.main()
