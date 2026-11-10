"""renderer 模块测试：天空渐变、递归深度上限、阴影射线、渲染主循环。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.geometry import HittableList, Plane, Sphere
from raytracer.materials import Glass, Lambert, Metal
from raytracer.renderer import Light, Scene, Tracer, render
from raytracer.vec import Ray, Vec3


class CountingWorld(HittableList):
    """记录 hit 被调用次数的物体集合——用来验证递归上限真的生效。"""

    def __init__(self, objects=()):
        super().__init__(objects)
        self.hit_calls = 0

    def hit(self, ray, t_min=1e-4, t_max=math.inf):
        self.hit_calls += 1
        return super().hit(ray, t_min, t_max)


def mirror_tunnel():
    """两面相对的完美金属墙：光线会永远弹下去，除非深度上限截断。"""
    return CountingWorld([
        Plane(Vec3(0, 0, 0), Vec3(0, 0, 1), Metal((1, 1, 1), 0.0)),
        Plane(Vec3(0, 0, -10), Vec3(0, 0, 1), Metal((1, 1, 1), 0.0)),
    ])


def tiny_scene(with_occluder=True):
    """小场景：地面 + 可选遮挡球，用于阴影/渲染测试。"""
    objects = [Plane(Vec3(0, 0, 0), Vec3(0, 1, 0), Lambert((0.8, 0.8, 0.8)))]
    if with_occluder:
        objects.append(Sphere(Vec3(0.2, 0.6, 0), 0.3, Metal((0.9, 0.9, 0.9), 0.0)))
    return Scene(
        name="tiny",
        world=HittableList(objects),
        look_from=Vec3(-1.5, 3.0, 2.5),
        look_at=Vec3(0, 0, 0),
        vfov=45.0,
        lights=[Light(Vec3(0.4, 1.0, 0.0), Vec3(1, 1, 1), 1.0)],
        ambient=Vec3(0.1, 0.1, 0.1),
        sky_top=Vec3(0.3, 0.5, 0.9),
        sky_bottom=Vec3(1.0, 1.0, 1.0),
    )


class TestSky(unittest.TestCase):
    def test_gradient_from_bottom_to_top(self):
        tracer = Tracer(
            HittableList(),
            sky_top=Vec3(0.2, 0.4, 0.6),
            sky_bottom=Vec3(1.0, 1.0, 1.0),
        )
        top = tracer.sky(Vec3(0, 1, 0))
        bottom = tracer.sky(Vec3(0, -1, 0))
        horizon = tracer.sky(Vec3(1, 0, 0))
        for g, w in zip(top, (0.2, 0.4, 0.6)):
            self.assertAlmostEqual(g, w, places=12)
        for g, w in zip(bottom, (1.0, 1.0, 1.0)):
            self.assertAlmostEqual(g, w, places=12)
        for g, w in zip(horizon, (0.6, 0.7, 0.8)):  # 中点 = 两端平均
            self.assertAlmostEqual(g, w, places=12)


class TestRecursionLimit(unittest.TestCase):
    def test_depth_zero_returns_black_without_touching_world(self):
        world = mirror_tunnel()
        tracer = Tracer(world, max_depth=8)
        color = tracer.ray_color(Ray(Vec3(0, 0, -5), Vec3(0, 0, 1)), depth=0)
        self.assertEqual(color.to_tuple(), (0.0, 0.0, 0.0))
        self.assertEqual(world.hit_calls, 0)  # 深度用完：连求交都不做

    def test_mirror_tunnel_bounces_exactly_max_depth_times(self):
        for depth in (1, 3, 6):
            world = mirror_tunnel()
            tracer = Tracer(world, max_depth=depth)
            tracer.ray_color(Ray(Vec3(0, 0, -5), Vec3(0, 0, 1)))
            self.assertEqual(world.hit_calls, depth)  # 每弹一次恰好一次求交

    def test_deep_tunnel_still_terminates(self):
        world = mirror_tunnel()  # 没有上限的话这条光线永远弹下去
        tracer = Tracer(world, max_depth=12)
        color = tracer.ray_color(Ray(Vec3(0, 0, -5), Vec3(0, 0, 1)))
        self.assertEqual(world.hit_calls, 12)
        self.assertGreaterEqual(color.x, 0.0)


class TestShadowRays(unittest.TestCase):
    def test_occluded_passes_through_glass_but_hits_metal(self):
        glass = Glass(ior=1.5)
        metal = Metal((1, 1, 1), 0.0)
        origin, direction = Vec3(0, 0, 3), Vec3(0, 0, -1)

        through_glass_only = Tracer(HittableList([Sphere(Vec3(0, 0, 0), 1.0, glass)]))
        self.assertFalse(through_glass_only.occluded(origin, direction))  # 玻璃放行

        glass_then_metal = Tracer(HittableList([
            Sphere(Vec3(0, 0, 0), 1.0, glass),
            Sphere(Vec3(0, 0, -5), 1.0, metal),
        ]))
        self.assertTrue(glass_then_metal.occluded(origin, direction))  # 玻璃后面有金属

        metal_only = Tracer(HittableList([Sphere(Vec3(0, 0, 0), 1.0, metal)]))
        self.assertTrue(metal_only.occluded(origin, direction))

    def test_shadow_removes_direct_light(self):
        to_light = Vec3(0.4, 1.0, 0.0).normalized()
        ray = Ray(Vec3(-1.5, 3.0, 2.5), Vec3(1.5, -3.0, -2.5).normalized())

        shadowed = Tracer(tiny_scene(with_occluder=True).world,
                          lights=[Light(Vec3(0.4, 1.0, 0.0))],
                          ambient=Vec3(0.1, 0.1, 0.1))
        color_in_shadow = shadowed.ray_color(ray)
        # 挡住后只剩环境光：albedo 0.8 × 0.1
        for g in color_in_shadow:
            self.assertAlmostEqual(g, 0.08, places=6)

        lit = Tracer(tiny_scene(with_occluder=False).world,
                     lights=[Light(Vec3(0.4, 1.0, 0.0))],
                     ambient=Vec3(0.1, 0.1, 0.1))
        color_lit = lit.ray_color(ray)
        ndotl = to_light.y  # 地面法线 (0,1,0) · to_light
        expected = 0.8 * (0.1 + ndotl)
        for g in color_lit:
            self.assertAlmostEqual(g, expected, places=6)
        self.assertGreater(color_lit.x, color_in_shadow.x)  # 有影比没影暗


class TestRenderLoop(unittest.TestCase):
    def test_output_size_range_and_progress(self):
        scene = tiny_scene()
        progress = []
        fb = render(scene, 12, 7, samples=2, max_depth=3, seed=0,
                    on_progress=lambda done, total: progress.append((done, total)))
        self.assertEqual(len(fb), 12 * 7 * 3)
        self.assertTrue(all(math.isfinite(v) and v >= 0.0 for v in fb))
        self.assertGreater(max(fb), 0.5)          # 天空很亮
        self.assertEqual(len(progress), 7)        # 每行回调一次
        self.assertEqual(progress[-1], (7, 7))

    def test_same_seed_is_reproducible(self):
        scene = tiny_scene()
        a = render(scene, 8, 5, samples=2, max_depth=4, seed=7)
        b = render(scene, 8, 5, samples=2, max_depth=4, seed=7)
        self.assertEqual(a, b)

    def test_bad_parameters_raise(self):
        scene = tiny_scene()
        with self.assertRaises(ValueError):
            render(scene, 0, 5, samples=1)
        with self.assertRaises(ValueError):
            render(scene, 5, 5, samples=0)


if __name__ == "__main__":
    unittest.main()
