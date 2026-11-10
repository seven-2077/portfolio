"""camera 模块测试：针孔朝向、视场角、宽高比、像素内抖动。"""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.camera import Camera
from raytracer.vec import Vec3


def make_camera(vfov=90.0, aspect=1.0):
    return Camera(
        look_from=Vec3(0, 0, 1),
        look_at=Vec3(0, 0, 0),
        vup=Vec3(0, 1, 0),
        vfov_deg=vfov,
        aspect=aspect,
    )


class TestCamera(unittest.TestCase):
    def test_center_ray_aims_at_target(self):
        cam = make_camera()
        ray = cam.get_ray(0.5, 0.5)
        # 中心视线应指向 look_at，即 -z 方向
        self.assertAlmostEqual(ray.direction.x, 0.0, places=12)
        self.assertAlmostEqual(ray.direction.y, 0.0, places=12)
        self.assertAlmostEqual(ray.direction.z, -1.0, places=12)
        self.assertEqual(ray.origin.to_tuple(), (0.0, 0.0, 1.0))

    def test_vfov_controls_edge_angle(self):
        # 90° 垂直视场：视口上缘恰好 45°（tan45 = 视口半高 / 焦距 1）
        cam = make_camera(vfov=90.0)
        top = cam.get_ray(0.5, 1.0).direction
        angle = math.degrees(math.atan2(top.y, -top.z))
        self.assertAlmostEqual(angle, 45.0, places=9)

        narrow = make_camera(vfov=30.0)
        top_narrow = narrow.get_ray(0.5, 1.0).direction
        angle_narrow = math.degrees(math.atan2(top_narrow.y, -top_narrow.z))
        self.assertAlmostEqual(angle_narrow, 15.0, places=9)

    def test_aspect_ratio_scales_viewport_width(self):
        cam = make_camera(vfov=60.0, aspect=2.5)
        self.assertAlmostEqual(cam.horizontal.length(), 2.5 * cam.vertical.length(), places=12)

    def test_pixel_uv_jitter_stays_inside_pixel(self):
        cam = make_camera()
        rng = random.Random(0)
        width, height = 10, 6
        for x, y in ((0, 0), (3, 2), (9, 5)):
            for _ in range(5):
                u, v = cam.pixel_uv(x, y, width, height, rng)
                self.assertGreaterEqual(u, x / width)
                self.assertLess(u, (x + 1) / width)
                # 图像 y=0 是顶行，v 轴向上：v ∈ (1-(y+1)/h, 1-y/h]
                self.assertGreater(v, 1.0 - (y + 1) / height)
                self.assertLessEqual(v, 1.0 - y / height)

    def test_ray_for_pixel_returns_unit_direction(self):
        cam = make_camera(aspect=16 / 9)
        rng = random.Random(1)
        for x, y in ((0, 0), (7, 4), (15, 8)):
            ray = cam.ray_for_pixel(x, y, 16, 9, rng)
            self.assertAlmostEqual(ray.direction.length(), 1.0, places=12)
            self.assertEqual(ray.origin.to_tuple(), (0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
