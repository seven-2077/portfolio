"""vec 模块测试：向量运算、反射、Snell 折射（含全反射）。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.vec import (Ray, Vec3, as_vec3, cross, dot, lerp, reflect,
                           refract)


class TestVec3Arithmetic(unittest.TestCase):
    def test_add_sub_and_scalar_mul(self):
        a, b = Vec3(1, 2, 3), Vec3(4, 5, 6)
        self.assertEqual((a + b).to_tuple(), (5.0, 7.0, 9.0))
        self.assertEqual((b - a).to_tuple(), (3.0, 3.0, 3.0))
        self.assertEqual((a * 2).to_tuple(), (2.0, 4.0, 6.0))
        self.assertEqual((3 * a).to_tuple(), (3.0, 6.0, 9.0))
        self.assertEqual((a / 2).to_tuple(), (0.5, 1.0, 1.5))
        self.assertEqual((-a).to_tuple(), (-1.0, -2.0, -3.0))

    def test_componentwise_mul(self):
        red, dim = Vec3(0.8, 0.2, 0.1), Vec3(0.5, 0.5, 0.5)
        self.assertEqual((red * dim).to_tuple(), (0.4, 0.1, 0.05))

    def test_dot_and_cross(self):
        i, j, k = Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1)
        self.assertAlmostEqual(i.dot(j), 0.0)          # 正交
        self.assertAlmostEqual(Vec3(1, 2, 3).dot(Vec3(4, -5, 6)), 4 - 10 + 18)
        self.assertEqual(i.cross(j).to_tuple(), k.to_tuple())   # i × j = k
        self.assertEqual(j.cross(i).to_tuple(), (-k).to_tuple())  # 反序变号

    def test_length_and_normalize(self):
        v = Vec3(3, 4, 0)
        self.assertAlmostEqual(v.length_squared(), 25.0)
        self.assertAlmostEqual(v.length(), 5.0)
        u = v.normalized()
        self.assertAlmostEqual(u.length(), 1.0, places=12)
        self.assertTrue(Vec3(0, 0, 0).normalized().near_zero())  # 零向量安全

    def test_as_vec3_accepts_tuple_and_vec(self):
        self.assertEqual(as_vec3((1, 2, 3)).to_tuple(), (1.0, 2.0, 3.0))
        v = Vec3(4, 5, 6)
        self.assertIs(as_vec3(v), v)

    def test_unpack_and_index(self):
        a, b, c = Vec3(7, 8, 9)
        self.assertEqual((a, b, c), (7.0, 8.0, 9.0))
        self.assertEqual(Vec3(7, 8, 9)[1], 8.0)


class TestReflect(unittest.TestCase):
    def test_flat_incidence_bounces_back(self):
        r = reflect(Vec3(0, -1, 0), Vec3(0, 1, 0))
        self.assertAlmostEqual(r.y, 1.0, places=12)
        self.assertAlmostEqual(r.length(), 1.0, places=12)

    def test_45_degree_reflection(self):
        r = reflect(Vec3(1, -1, 0).normalized(), Vec3(0, 1, 0))
        expected = Vec3(1, 1, 0).normalized()
        for got, want in zip(r, expected):
            self.assertAlmostEqual(got, want, places=12)


class TestRefract(unittest.TestCase):
    def test_normal_incidence_goes_straight(self):
        # 空气→玻璃，正入射：方向不变
        t = refract(Vec3(0, 0, -1), Vec3(0, 0, 1), 1.0 / 1.5)
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.z, -1.0, places=12)
        self.assertAlmostEqual(t.length(), 1.0, places=12)

    def test_obeys_snell_law(self):
        n1, n2 = 1.0, 1.5
        theta1 = math.radians(45.0)
        incident = Vec3(math.sin(theta1), 0.0, -math.cos(theta1))
        normal = Vec3(0, 0, 1)
        t = refract(incident, normal, n1 / n2)
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.length(), 1.0, places=12)
        theta2 = math.acos(max(-1.0, min(1.0, -t.dot(normal))))
        # n1·sinθ1 = n2·sinθ2
        self.assertAlmostEqual(n1 * math.sin(theta1), n2 * math.sin(theta2), places=10)
        self.assertLess(theta2, theta1)   # 进入光密介质，偏向法线
        self.assertAlmostEqual(t.y, 0.0, places=12)  # 仍在入射面内
        self.assertGreater(t.x, 0.0)

    def test_total_internal_reflection(self):
        # 玻璃→空气，60° 入射 > 临界角 ≈ 41.8°：折射分支死亡
        theta = math.radians(60.0)
        incident = Vec3(math.sin(theta), 0.0, math.cos(theta))
        normal = Vec3(0, 0, -1)  # 与入射方向相向
        self.assertIsNone(refract(incident, normal, 1.5))

    def test_reflection_weight_is_energy_conserving_at_tir_boundary(self):
        # 临界角处折射光线几乎沿界面（k → 0），长度仍为 1
        eta = 1.5
        theta_c = math.asin(1.0 / eta)
        incident = Vec3(math.sin(theta_c), 0.0, math.cos(theta_c))
        t = refract(incident, Vec3(0, 0, -1), eta)
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.length(), 1.0, places=9)


class TestRay(unittest.TestCase):
    def test_ray_at(self):
        ray = Ray(Vec3(1, 2, 3), Vec3(0, 1, 0).normalized())
        self.assertEqual(ray.at(0.0).to_tuple(), (1.0, 2.0, 3.0))
        self.assertEqual(ray.at(5.0).to_tuple(), (1.0, 7.0, 3.0))


class TestLerp(unittest.TestCase):
    def test_endpoints_and_midpoint(self):
        a, b = Vec3(0, 0, 0), Vec3(2, 4, 6)
        self.assertEqual(lerp(a, b, 0.0).to_tuple(), (0.0, 0.0, 0.0))
        self.assertEqual(lerp(a, b, 1.0).to_tuple(), (2.0, 4.0, 6.0))
        self.assertEqual(lerp(a, b, 0.5).to_tuple(), (1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main()
