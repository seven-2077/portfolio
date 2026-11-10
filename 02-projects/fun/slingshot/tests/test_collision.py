"""碰撞检测与响应：分离无穿插、地面、反弹、摩擦。"""
import unittest

from physics.collision import (
    Box,
    Circle,
    box_box,
    circle_box,
    ground_contact,
    resolve,
    resolve_ground,
)
from physics.verlet import Particle

DT = 1.0 / 120.0


def _box(x, y, hw=1.0, hh=1.0, inv_mass=1.0):
    p = Particle(x, y, x, y, inv_mass)
    return Box(p, hw, hh)


def _circle(x, y, r=1.0, inv_mass=1.0):
    p = Particle(x, y, x, y, inv_mass)
    return Circle(p, r)


class TestCircleBox(unittest.TestCase):
    def test_overlap_detected_with_depth(self):
        c = _circle(1.5, 0.0, r=1.0)
        b = _box(0.0, 0.0)
        contact = circle_box(c, b)
        self.assertIsNotNone(contact)
        self.assertAlmostEqual(contact.depth, 0.5, places=9)
        self.assertAlmostEqual(contact.nx, 1.0, places=9)

    def test_resolve_separates_completely(self):
        """分离后不得再有穿插（无穿插断言）。"""
        c = _circle(1.5, 0.0, r=1.0)
        b = _box(0.0, 0.0)
        contact = circle_box(c, b)
        resolve(contact, DT)
        self.assertIsNone(circle_box(c, b))

    def test_separated_pair_no_contact(self):
        self.assertIsNone(circle_box(_circle(3.0, 0.0), _box(0.0, 0.0)))

    def test_center_inside_pushed_out_min_axis(self):
        """圆心陷入盒内时沿最小穿透轴推出。"""
        c = _circle(0.2, 0.0, r=1.0)
        b = _box(0.0, 0.0)
        contact = circle_box(c, b)
        self.assertAlmostEqual(contact.nx, 1.0, places=9)
        resolve(contact, DT)
        self.assertIsNone(circle_box(c, b))


class TestBoxBox(unittest.TestCase):
    def test_min_penetration_axis(self):
        a = _box(0.0, 0.0)
        b = _box(1.5, 0.3)  # x 方向穿透 0.5 < y 方向 1.7
        contact = box_box(a, b)
        self.assertAlmostEqual(contact.nx, 1.0, places=9)
        self.assertEqual(contact.ny, 0.0)

    def test_resolve_box_box_no_overlap(self):
        a = _box(0.0, 0.0)
        b = _box(1.5, 0.3)
        resolve(box_box(a, b), DT)
        self.assertIsNone(box_box(a, b))

    def test_equal_mass_split_is_symmetric(self):
        a = _box(0.0, 0.0)
        b = _box(1.5, 0.0)
        resolve(box_box(a, b), DT)
        # 对称分离：各挪一半
        self.assertAlmostEqual(a.p.x, -0.25, places=9)
        self.assertAlmostEqual(b.p.x, 1.75, places=9)


class TestGround(unittest.TestCase):
    GROUND = 28.0

    def test_falling_body_lifted_out(self):
        c = _circle(5.0, 28.3, r=0.5)
        self.assertAlmostEqual(ground_contact(c, self.GROUND), 0.8, places=9)
        resolve_ground(c, self.GROUND, DT)
        self.assertIsNone(ground_contact(c, self.GROUND))

    def test_fast_impact_bounces_up(self):
        c = _circle(5.0, 28.3, r=0.5)
        c.p.set_velocity(0.0, 5.0, DT)
        j = resolve_ground(c, self.GROUND, DT)
        self.assertGreater(j, 0.0)
        vx, vy = c.p.velocity(DT)
        self.assertLess(vy, 0.0)  # 反弹向上（y 轴向下）

    def test_slow_contact_dead_stop_no_damage(self):
        """缓慢着地死停：速度清零、不返回冲量（静置不磨损）。"""
        c = _circle(5.0, 28.3, r=0.5)
        c.p.set_velocity(0.0, 0.3, DT)
        j = resolve_ground(c, self.GROUND, DT)
        self.assertEqual(j, 0.0)
        _, vy = c.p.velocity(DT)
        self.assertEqual(vy, 0.0)

    def test_friction_slows_sliding(self):
        b = _box(5.0, 27.5, hh=1.0)  # 底边 28.5 沉入地面
        b.p.set_velocity(4.0, 0.0, DT)
        for _ in range(10):
            b.p.translate(0.0, 0.05)  # 模拟重力每步把物体压回地面
            resolve_ground(b, self.GROUND, DT)
        vx, _ = b.p.velocity(DT)
        self.assertLess(abs(vx), 4.0 * 0.6)
        self.assertIsNone(ground_contact(b, self.GROUND))


if __name__ == "__main__":
    unittest.main()
