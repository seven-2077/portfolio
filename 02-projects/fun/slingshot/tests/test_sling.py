"""弹弓：拉伸/力度、皮筋约束、轨迹预测与实射一致。"""
import math
import unittest

from game import level as lvl
from game.sling import K, MAX_STRETCH, Slingshot
from game.world import World


def empty_world() -> World:
    """无结构的空世界（弹道只有重力，便于对照）。"""
    return World(lvl.make_spec([]))


class TestAim(unittest.TestCase):
    def test_pull_clamps_power_and_stretch(self):
        w = empty_world()
        s = Slingshot(w)
        s.pull(45, 1.7)  # 超上限
        p = w.projectile.p
        stretch = math.hypot(p.x - w.anchor[0], p.y - w.anchor[1])
        self.assertLessEqual(stretch, MAX_STRETCH + 1e-9)
        vx, vy = s.pull(45, -0.5)  # 低于下限
        self.assertEqual((vx, vy), (0.0, 0.0))

    def test_pull_direction_matches_angle(self):
        """90° 拉满：弹丸在锚点正下方，出膛速度垂直向上。"""
        w = empty_world()
        s = Slingshot(w)
        vx, vy = s.pull(90, 1.0)
        p = w.projectile.p
        self.assertAlmostEqual(p.x, w.anchor[0], places=9)
        self.assertAlmostEqual(p.y, w.anchor[1] + MAX_STRETCH, places=6)
        self.assertLess(vy, 0.0)  # y 轴向下，向上发射为负
        self.assertAlmostEqual(math.hypot(vx, vy), K * MAX_STRETCH, places=6)

    def test_band_constraints_hold_projectile(self):
        """皮筋 = 两个距离约束：拉弓后端点距离不超皮筋原长。"""
        w = empty_world()
        Slingshot(w).pull(60, 0.95)
        self.assertEqual(len(w.bands), 2)
        p = w.projectile.p
        for band in w.bands:
            d = math.hypot(p.x - band.a.x, p.y - band.a.y)
            self.assertLessEqual(d, band.rest + 1e-9)


class TestTrajectoryPrediction(unittest.TestCase):
    def test_prediction_matches_real_shot(self):
        """轨迹预演（无碰撞 Verlet）与实射前 110 步逐点一致。"""
        w = empty_world()
        s = Slingshot(w)
        pred = s.predict(60, 0.7)
        self.assertGreater(len(pred), 100)
        s.release(60, 0.7)
        for i, (ex, ey) in enumerate(pred):
            w.step()
            self.assertIsNotNone(w.projectile, f"第 {i} 步弹丸不应消失")
            p = w.projectile.p
            self.assertAlmostEqual(p.x, ex, places=9)
            self.assertAlmostEqual(p.y, ey, places=9)

    def test_prediction_follows_parabola_apex(self):
        """预演轨迹呈抛物线：先升后降、顶点唯一。"""
        w = empty_world()
        s = Slingshot(w)
        pred = s.predict(60, 0.7)
        ys = [y for _, y in pred]
        apex = min(ys)
        self.assertLess(apex, 17.0)  # 起点 y=24，应明显先上升
        self.assertGreater(apex, 13.0)  # 顶点又不能高过头顶
        i = ys.index(apex)
        self.assertTrue(all(ys[k] <= ys[k - 1] for k in range(1, i + 1)), "上升段 y 应递减")
        self.assertTrue(all(ys[k] >= ys[k - 1] for k in range(i + 1, len(ys))), "下降段 y 应递增")

    def test_release_consumes_ammo_once(self):
        w = empty_world()
        s = Slingshot(w)
        s.release(45, 0.8)
        self.assertEqual(w.ammo_spent, 1)
        self.assertFalse(w.spawn())  # 飞行中不可再上弹
        self.assertEqual(w.ammo_spent, 1)


if __name__ == "__main__":
    unittest.main()
