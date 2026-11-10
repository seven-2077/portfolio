"""geometry 模块测试：球/平面求交、法线朝向、最近命中调度。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.geometry import HittableList, Plane, Sphere
from raytracer.materials import Lambert, Metal
from raytracer.vec import Ray, Vec3

RED = Lambert((1.0, 0.0, 0.0))
SHINY = Metal((0.9, 0.9, 0.9))


class TestSphere(unittest.TestCase):
    def setUp(self):
        self.sphere = Sphere(Vec3(0, 0, 0), 1.0, RED)

    def test_hit_returns_nearest_root(self):
        ray = Ray(Vec3(0, 0, -5), Vec3(0, 0, 1))
        rec = self.sphere.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.t, 4.0, places=12)          # -5 → -1，走 4 个单位
        self.assertAlmostEqual(rec.point.z, -1.0, places=12)
        self.assertTrue(rec.front_face)                        # 从外面打进去
        for got, want in zip(rec.normal, (0, 0, -1)):          # 法线与射线相向
            self.assertAlmostEqual(got, want, places=12)
        self.assertIs(rec.material, RED)

    def test_miss_when_ray_passes_beside(self):
        ray = Ray(Vec3(0, 2, -5), Vec3(0, 0, 1))
        self.assertIsNone(self.sphere.hit(ray, 1e-4, math.inf))

    def test_tangent_ray_still_hits(self):
        # 判别式恰为 0：圆与射线相切
        ray = Ray(Vec3(0, 1, -5), Vec3(0, 0, 1))
        rec = self.sphere.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.t, 5.0, places=12)
        self.assertAlmostEqual(rec.point.y, 1.0, places=12)

    def test_sphere_behind_ray_is_a_miss(self):
        ray = Ray(Vec3(0, 0, 5), Vec3(0, 0, 1))  # 球在背后
        self.assertIsNone(self.sphere.hit(ray, 1e-4, math.inf))

    def test_shot_from_inside_hits_far_root_with_flipped_normal(self):
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, 1))
        rec = self.sphere.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.t, 1.0, places=12)
        self.assertFalse(rec.front_face)                       # 从内部打出去
        for got, want in zip(rec.normal, (0, 0, -1)):          # 法线被翻回迎着射线
            self.assertAlmostEqual(got, want, places=12)

    def test_t_max_bounds_the_hit(self):
        ray = Ray(Vec3(0, 0, -5), Vec3(0, 0, 1))
        self.assertIsNone(self.sphere.hit(ray, 1e-4, 2.0))     # 近根 4 超出上限
        self.assertIsNotNone(self.sphere.hit(ray, 1e-4, 6.0))


class TestPlane(unittest.TestCase):
    def setUp(self):
        self.plane = Plane(Vec3(0, 0, 0), Vec3(0, 1, 0), RED)  # 地面

    def test_hit_from_above(self):
        ray = Ray(Vec3(0, 2, 0), Vec3(0, -1, 0))
        rec = self.plane.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.t, 2.0, places=12)
        self.assertTrue(rec.front_face)
        self.assertAlmostEqual(rec.normal.y, 1.0, places=12)

    def test_hit_from_below_flips_normal(self):
        ray = Ray(Vec3(0, -1, 0), Vec3(0, 1, 0))
        rec = self.plane.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertFalse(rec.front_face)
        self.assertAlmostEqual(rec.normal.y, -1.0, places=12)  # 迎着射线

    def test_parallel_ray_misses(self):
        ray = Ray(Vec3(0, 1, 0), Vec3(1, 0, 0))
        self.assertIsNone(self.plane.hit(ray, 1e-4, math.inf))

    def test_ray_pointing_away_misses(self):
        ray = Ray(Vec3(0, 1, 0), Vec3(0, 1, 0))
        self.assertIsNone(self.plane.hit(ray, 1e-4, math.inf))  # 交点在背后


class TestHittableList(unittest.TestCase):
    def test_returns_nearest_hit(self):
        near = Sphere(Vec3(0, 0, 0), 1.0, RED)
        far = Sphere(Vec3(0, 0, 3), 1.0, SHINY)
        world = HittableList([far, near])  # 故意先放远的
        ray = Ray(Vec3(0, 0, -5), Vec3(0, 0, 1))
        rec = world.hit(ray, 1e-4, math.inf)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.t, 4.0, places=12)
        self.assertIs(rec.material, RED)                       # 近的赢

    def test_miss_returns_none(self):
        world = HittableList([Sphere(Vec3(0, 0, 0), 1.0, RED)])
        ray = Ray(Vec3(0, 9, -5), Vec3(0, 0, 1))
        self.assertIsNone(world.hit(ray, 1e-4, math.inf))

    def test_empty_world_misses(self):
        world = HittableList()
        ray = Ray(Vec3(0, 0, 0), Vec3(0, 0, 1))
        self.assertIsNone(world.hit(ray, 1e-4, math.inf))


if __name__ == "__main__":
    unittest.main()
