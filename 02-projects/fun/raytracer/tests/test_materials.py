"""materials 模块测试：Lambert 直接光、金属反射与抖动、玻璃分光/全反射。"""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.geometry import HitRecord
from raytracer.materials import (Glass, Lambert, Metal, fresnel_reflectance,
                                 schlick_reflectance)
from raytracer.vec import Ray, Vec3

SIN45 = math.sqrt(0.5)


def make_hit(normal_out, ray_dir, material, front_face=None, t=1.0, point=None):
    """构造一个 HitRecord：front_face 默认按法线与射线方向自动推断。"""
    if front_face is None:
        front_face = Vec3(*ray_dir).dot(Vec3(*normal_out)) < 0.0
    normal = Vec3(*normal_out) if front_face else -Vec3(*normal_out)
    return HitRecord(point or Vec3(0, 0, 0), normal, t, front_face, material)


class TestLambert(unittest.TestCase):
    def test_uses_direct_light_and_casts_shadow(self):
        m = Lambert((1, 1, 1))
        self.assertTrue(m.uses_direct_light)
        self.assertTrue(m.casts_shadow)
        self.assertEqual(m.scatter(Ray(Vec3(0, 0, 0), Vec3(0, 1, 0)),
                                   make_hit((0, 1, 0), (0, -1, 0), m),
                                   random.Random(0)), ())  # 漫反射不进递归

    def test_shade_is_albedo_times_light(self):
        m = Lambert((0.5, 0.25, 1.0))
        hit = make_hit((0, 1, 0), (0, -1, 0), m)
        got = m.shade_direct(hit, Vec3(0.4, 0.4, 0.4))
        for g, w in zip(got, (0.2, 0.1, 0.4)):
            self.assertAlmostEqual(g, w, places=12)


class TestMetal(unittest.TestCase):
    def test_pure_metal_reflects_exactly(self):
        m = Metal((0.8, 0.7, 0.6), roughness=0.0)
        incident = Vec3(SIN45, -SIN45, 0)
        hit = make_hit((0, 1, 0), incident.to_tuple(), m)
        events = m.scatter(Ray(hit.point, incident), hit, random.Random(0))
        self.assertEqual(len(events), 1)
        ray, weight = events[0]
        expected = Vec3(SIN45, SIN45, 0)  # 关于 y=0 面对称弹起
        for g, w in zip(ray.direction, expected):
            self.assertAlmostEqual(g, w, places=12)
        self.assertEqual(weight.to_tuple(), (0.8, 0.7, 0.6))  # 颜色 = 反照率
        self.assertFalse(m.uses_direct_light)  # 金属不吃直射光，全靠反射成像

    def test_fuzzed_direction_stays_unit_and_above_surface(self):
        m = Metal((1, 1, 1), roughness=0.35)
        rng = random.Random(42)
        incident = Vec3(SIN45, -SIN45, 0)
        hit = make_hit((0, 1, 0), incident.to_tuple(), m)
        for _ in range(30):
            events = m.scatter(Ray(hit.point, incident), hit, rng)
            self.assertEqual(len(events), 1)
            direction = events[0][0].direction
            self.assertAlmostEqual(direction.length(), 1.0, places=10)
            self.assertGreater(direction.dot(hit.normal), 0.0)  # 只朝上半球

    def test_roughness_is_clamped(self):
        self.assertEqual(Metal((1, 1, 1), roughness=7.0).roughness, 1.0)
        self.assertEqual(Metal((1, 1, 1), roughness=-3.0).roughness, 0.0)


class TestGlass(unittest.TestCase):
    def test_normal_incidence_splits_4_percent(self):
        m = Glass(ior=1.5)
        incident = Vec3(0, 0, -1)
        hit = make_hit((0, 0, 1), (0, 0, -1), m)  # 正面入射
        events = m.scatter(Ray(hit.point, incident), hit, random.Random(0))
        self.assertEqual(len(events), 2)
        (refl_ray, refl_w), (refr_ray, refr_w) = events
        self.assertAlmostEqual(refl_w.x, 0.04, places=12)          # r0 = (0.2)²
        self.assertAlmostEqual(refr_w.x, 0.96, places=12)          # 能量守恒
        self.assertAlmostEqual(refr_ray.direction.z, -1.0, places=12)  # 正入射不偏折
        self.assertAlmostEqual(refl_w.x + refr_w.x, 1.0, places=12)
        self.assertFalse(m.casts_shadow)  # 玻璃不投影

    def test_tint_attenuates_only_transmitted_ray(self):
        m = Glass(ior=1.5, tint=(0.5, 0.8, 1.0))
        hit = make_hit((0, 0, 1), (0, 0, -1), m)
        events = m.scatter(Ray(hit.point, Vec3(0, 0, -1)), hit, random.Random(0))
        _, refl_w = events[0]
        _, refr_w = events[1]
        self.assertAlmostEqual(refl_w.x, 0.04, places=12)          # 反射不被染色
        for g, w in zip(refr_w, (0.5 * 0.96, 0.8 * 0.96, 0.96)):
            self.assertAlmostEqual(g, w, places=12)

    def test_total_internal_reflection_uses_single_reflected_ray(self):
        m = Glass(ior=1.5)
        # 从玻璃内部以 60° 射向界面（临界角 ≈ 41.8°）→ 全反射
        # 界面朝外的法线是 +z，射线也朝 +z ⇒ front_face 自动推断为 False
        incident = Vec3(math.sin(math.radians(60)), 0.0, math.cos(math.radians(60)))
        hit = make_hit((0, 0, 1), incident.to_tuple(), m)
        events = m.scatter(Ray(hit.point, incident), hit, random.Random(0))
        self.assertEqual(len(events), 1)                           # 折射分支消失
        ray, weight = events[0]
        self.assertEqual(weight.to_tuple(), (1.0, 1.0, 1.0))       # 100% 能量
        # 反射方向 = 入射关于界面法线对称：z 分量反向
        self.assertAlmostEqual(ray.direction.x, incident.x, places=12)
        self.assertAlmostEqual(ray.direction.z, -incident.z, places=12)

    def test_exact_fresnel_differs_from_schlick_at_45_degrees(self):
        eta = 1.0 / 1.5
        cos_i = SIN45
        exact = fresnel_reflectance(cos_i, eta)
        approx = schlick_reflectance(cos_i, eta)
        self.assertAlmostEqual(exact, 0.05024, places=4)   # 手算参考值
        self.assertAlmostEqual(approx, 0.04207, places=4)
        self.assertGreater(abs(exact - approx), 0.005)     # 两种算法确实不同
        # 通过材质开关切换
        glass = Glass(ior=1.5, schlick=False)
        self.assertAlmostEqual(glass.reflectance(cos_i, eta), exact, places=12)

    def test_grazing_incidence_reflects_almost_everything(self):
        self.assertGreater(fresnel_reflectance(0.0, 1.0 / 1.5), 0.99)
        self.assertGreater(schlick_reflectance(0.0, 1.0 / 1.5), 0.99)

    def test_normal_incidence_reflectance_is_r0_for_both_models(self):
        for fn in (schlick_reflectance, fresnel_reflectance):
            self.assertAlmostEqual(fn(1.0, 1.0 / 1.5), 0.04, places=12)


if __name__ == "__main__":
    unittest.main()
