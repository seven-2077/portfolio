"""trace.py 单元测试：初值微差、初值敏感性（分岔）、端点轨迹采集。"""

from __future__ import annotations

import math
import unittest

from pendulum import energy, trace
from pendulum.ode import DEFAULT

# 与 demo 一致的高能初值：θ1 = 170°, θ2 = -120°，静止释放
BASE = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)


class TestPairSetup(unittest.TestCase):
    def test_pair_initial_distance_equals_delta(self):
        """两组初值只差 delta：逐帧距离的第一帧就是 1e-4。"""
        pair = trace.run_pair_with_delta(BASE, delta=1e-4, t_end=0.5, dt=1e-3)
        self.assertAlmostEqual(pair.initial_distance, 1e-4, places=9)
        self.assertEqual(len(pair.distances), len(pair.times))

    def test_identical_runs_never_diverge(self):
        """同一初值积分两遍 → 距离恒 0，分岔时刻为 None（对照组）。"""
        pair = trace.run_pair(BASE, BASE, t_end=2.0, dt=1e-3)
        self.assertTrue(all(d == 0.0 for d in pair.distances))
        self.assertIsNone(pair.bifurcation_time(0.1))


class TestInitialSensitivity(unittest.TestCase):
    """核心卖点断言：同样时长后，两组状态差异远大于初始差异。"""

    def test_divergence_grows_far_beyond_initial(self):
        pair = trace.run_pair_with_delta(BASE, delta=1e-4, t_end=4.0, dt=1e-3)
        t_star = pair.bifurcation_time(0.1)

        self.assertIsNotNone(t_star, "4s 内相空间距离应超过 0.1")
        self.assertLess(t_star, 4.0)
        # 终态差异 >> 初始差异（要求放大 1000 倍以上，实测 ~1e5 倍）
        self.assertGreater(pair.final_distance, 1000.0 * pair.initial_distance,
                           f"初始 {pair.initial_distance:.1e} → 终态 {pair.final_distance:.1e}")

    def test_divergence_is_monotone_in_early_phase(self):
        """早期距离应总体增长：末段均值远大于首段均值。"""
        pair = trace.run_pair_with_delta(BASE, delta=1e-4, t_end=4.0, dt=1e-3)
        head = sum(pair.distances[:50]) / 50
        tail = sum(pair.distances[-50:]) / 50
        self.assertGreater(tail, 100.0 * head)

    def test_smaller_delta_delays_but_does_not_prevent_divergence(self):
        """delta 缩小 10 倍，分岔推迟但依然发生（蝴蝶效应不因微小而消失）。"""
        pair_big = trace.run_pair_with_delta(BASE, delta=1e-3, t_end=6.0, dt=1e-3)
        pair_small = trace.run_pair_with_delta(BASE, delta=1e-4, t_end=6.0, dt=1e-3)
        t_big = pair_big.bifurcation_time(0.1)
        t_small = pair_small.bifurcation_time(0.1)
        self.assertIsNotNone(t_small)
        if t_big is not None:
            self.assertLessEqual(t_big, t_small + 1e-9)


class TestRunRecording(unittest.TestCase):
    def test_series_are_aligned_and_complete(self):
        run = trace.simulate(BASE, t_end=1.0, dt=1e-3)
        n = len(run.times)
        self.assertEqual(n, 1001)
        self.assertEqual(len(run.states), n)
        self.assertEqual(len(run.energies), n)
        self.assertEqual(len(run.tips), n)
        self.assertAlmostEqual(run.times[-1], 1.0, places=12)

    def test_tips_within_reach_of_pivot(self):
        """端点轨迹坐标不能超出杆长之和（√(x²+y²) ≤ l1+l2）。"""
        run = trace.simulate(BASE, t_end=1.0, dt=1e-3)
        reach = run.params.l1 + run.params.l2
        for x1, y1, x2, y2 in run.tips:
            self.assertLessEqual(math.hypot(x1, y1), reach + 1e-9)
            self.assertLessEqual(math.hypot(x2, y2), reach + 1e-9)

    def test_tip_matches_direct_computation(self):
        """tip_positions 与几何定义一致。"""
        s = (0.7, 0.0, -0.4, 0.0)
        x1, y1, x2, y2 = trace.tip_positions(s, DEFAULT)
        self.assertAlmostEqual(x1, math.sin(0.7), places=12)
        self.assertAlmostEqual(y1, -math.cos(0.7), places=12)
        self.assertAlmostEqual(x2, x1 + math.sin(-0.4), places=12)
        self.assertAlmostEqual(y2, y1 - math.cos(-0.4), places=12)

    def test_run_energy_series_matches_energy_module(self):
        run = trace.simulate(BASE, t_end=0.5, dt=1e-3)
        for t, s, e in zip(run.times, run.states, run.energies):
            self.assertAlmostEqual(e, energy.total(s, DEFAULT), places=12)
        self.assertLess(run.relative_energy_drift(), 1e-6)

    def test_state_distance_is_euclidean(self):
        self.assertAlmostEqual(
            trace.state_distance((0.0, 0.0, 0.0, 0.0), (3.0, 4.0, 0.0, 0.0)), 5.0)


if __name__ == "__main__":
    unittest.main()
