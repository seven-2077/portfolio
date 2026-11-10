"""Verlet 积分与约束：解析解对照、松弛收敛。"""
import math
import unittest

from physics.verlet import DistanceConstraint, Particle, Rope, step


class TestVerletIntegration(unittest.TestCase):
    def setUp(self):
        self.dt = 1.0 / 120.0

    def test_fall_matches_parabola(self):
        """自由落体 1 秒与解析解 ½gt² 相对误差 < 2%。"""
        g = 10.0
        p = Particle(0.0, 0.0, 0.0, 0.0)
        p.ay = g
        n = 120
        for _ in range(n):
            step([p], self.dt)
        t = n * self.dt
        exact = 0.5 * g * t * t
        self.assertLess(abs(p.y - exact) / exact, 0.02)

    def test_horizontal_motion_stays_constant(self):
        """水平方向无外力：匀速位移与解析解一致（速度只藏在位置差里）。"""
        v0 = 5.0
        p = Particle(0.0, 0.0, 0.0, 0.0)
        p.set_velocity(v0, 0.0, self.dt)
        for _ in range(120):
            step([p], self.dt, damping=1.0)  # 关闭阻尼看纯粹积分
        self.assertAlmostEqual(p.x, v0 * 1.0, places=9)
        self.assertAlmostEqual(p.y, 0.0, places=9)

    def test_smaller_dt_is_more_accurate(self):
        """误差随 dt 线性收敛（Verlet 一阶初速项）。"""
        errs = []
        for dt in (1.0 / 60.0, 1.0 / 120.0):
            p = Particle(0.0, 0.0, 0.0, 0.0)
            p.ay = 10.0
            n = int(round(1.0 / dt))
            for _ in range(n):
                step([p], dt)
            errs.append(abs(p.y - 5.0))
        self.assertLess(errs[1], errs[0])

    def test_fixed_particle_never_moves(self):
        p = Particle(3.0, 4.0, 3.0, 4.0, 0.0, fixed=True)
        p.ay = 10.0
        step([p], self.dt)
        self.assertEqual((p.x, p.y), (3.0, 4.0))


class TestConstraints(unittest.TestCase):
    def test_single_constraint_exact_after_one_solve(self):
        """两质点距离约束松弛一次即收敛（stiffness=1）。"""
        a = Particle(0.0, 0.0, 0.0, 0.0, 0.0)  # 锚点
        b = Particle(3.0, 0.0, 3.0, 0.0, 1.0)
        c = DistanceConstraint(a, b, 2.0)
        c.solve()
        dist = math.hypot(b.x - a.x, b.y - a.y)
        self.assertAlmostEqual(dist, 2.0, places=12)
        self.assertEqual((a.x, a.y), (0.0, 0.0))  # 固定端不动

    def test_fixed_anchor_respected(self):
        a = Particle(0.0, 0.0, 0.0, 0.0, 0.0, fixed=True)
        b = Particle(0.0, 5.0, 0.0, 5.0, 1.0)
        c = DistanceConstraint(a, b, 1.0, stiffness=0.5)
        for _ in range(50):
            c.solve()
        self.assertEqual((a.x, a.y), (0.0, 0.0))
        self.assertAlmostEqual(math.hypot(b.x, b.y), 1.0, places=6)

    def test_rope_chain_converges(self):
        """绳链（6 质点）迭代松弛收敛到等长。"""
        pts = [Particle(i * 1.4, 0.0, i * 1.4, 0.0, 0.0 if i == 0 else 1.0)
               for i in range(6)]
        rope = Rope(pts, segment=1.0)
        e_early = rope.solve(20)
        e_late = rope.solve(200)
        self.assertLess(e_late, 1e-6)
        self.assertLess(e_late, e_early)

    def test_solve_does_not_inject_velocity(self):
        """松弛只改坐标不改速度（pos/prev 同步），防止约束抖动。"""
        dt = 1.0 / 120.0
        a = Particle(0.0, 0.0, 0.0, 0.0, 0.0)
        b = Particle(4.0, 0.0, 4.0, 0.0, 1.0)
        b.set_velocity(2.0, -1.0, dt)
        va = b.velocity(dt)
        DistanceConstraint(a, b, 2.0).solve()
        self.assertAlmostEqual(math.hypot(b.x - a.x, b.y - a.y), 2.0, places=9)
        vb = b.velocity(dt)
        self.assertAlmostEqual(va[0], vb[0], places=9)
        self.assertAlmostEqual(va[1], vb[1], places=9)


if __name__ == "__main__":
    unittest.main()
