"""raycaster 测试：DDA 与几何法对照、鱼眼校正、纹理列采样、明暗、整屏渲染。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.loop import FrameBuffer
from fps.map import load_map
from fps.player import Player
from fps.raycaster import (MAX_DEPTH, MATERIALS, RayHit, SHADE_RAMP,
                           cast_ray, fisheye_correct, render_walls,
                           sample_texel, shade_char, texture_column)


def analytic_hit(gmap, ox, oy, angle):
    """几何法参考实现：对每堵墙的 AABB 做射线求交，取最小正 t。"""
    dir_x, dir_y = math.cos(angle), math.sin(angle)
    best = math.inf
    for cy in range(gmap.height):
        for cx in range(gmap.width):
            if not gmap.is_wall_cell(cx, cy):
                continue
            t_near, t_far = -math.inf, math.inf
            for lo, hi, origin, d in ((cx, cx + 1, ox, dir_x),
                                      (cy, cy + 1, oy, dir_y)):
                if abs(d) < 1e-15:
                    if origin < lo or origin > hi:
                        t_near = math.inf
                        break
                    continue
                t1, t2 = (lo - origin) / d, (hi - origin) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                t_near = max(t_near, t1)
                t_far = min(t_far, t2)
            if t_near <= t_far and t_far > 0 and t_near < best:
                best = max(t_near, 0.0)
    return best


class TestDDAAgainstGeometry(unittest.TestCase):
    """DDA 距离必须与「逐墙求交」的几何法一致（多角度多格）。"""

    ANGLES = [0.0, 0.37, 1.13, 1.5708, 2.21, 3.1416, 4.7, 5.55,
              6.283, -0.9, -2.4]

    def test_dda_matches_analytic_on_hand_maps(self):
        for map_name in ("crypt", "vault"):
            gmap = load_map(map_name)
            origins = [(1.5, 1.5), (gmap.spawn[0], gmap.spawn[1]),
                       (gmap.exit_pos[0], gmap.exit_pos[1])]
            for ox, oy in origins:
                if gmap.is_wall_at(ox, oy):
                    continue
                for angle in self.ANGLES:
                    with self.subTest(map=map_name, origin=(ox, oy),
                                      angle=round(angle, 3)):
                        hit = cast_ray(gmap, ox, oy, angle)
                        expected = analytic_hit(gmap, ox, oy, angle)
                        self.assertTrue(hit.hit)
                        self.assertAlmostEqual(hit.dist, expected, places=6)

    def test_dda_matches_analytic_on_random_map(self):
        from fps.map import generate_random_map
        gmap = generate_random_map(seed=11, width=13, height=11)
        for angle in self.ANGLES:
            with self.subTest(angle=round(angle, 3)):
                hit = cast_ray(gmap, 1.5, 1.5, angle)
                self.assertAlmostEqual(
                    hit.dist, analytic_hit(gmap, 1.5, 1.5, angle), places=6)

    def test_hit_reports_wall_cell_and_material(self):
        gmap = load_map("crypt")
        hit = cast_ray(gmap, 1.5, 1.5, math.pi)      # 向西，第 1 列西侧是边框墙
        self.assertTrue(hit.hit)
        self.assertEqual(hit.cell_x, 0)
        self.assertEqual(hit.material, gmap.cell(0, 1))
        self.assertTrue(gmap.is_wall_cell(hit.cell_x, hit.cell_y))
        self.assertGreaterEqual(hit.wall_x, 0.0)
        self.assertLess(hit.wall_x, 1.0)


class TestFisheye(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(fisheye_correct(10.0, 0.0), 10.0)
        self.assertAlmostEqual(fisheye_correct(10.0, math.pi / 3), 5.0)
        # 斜边永远大于等于直角边：校正只会缩短
        self.assertLess(fisheye_correct(10.0, 0.9), 10.0)

    def test_straight_wall_has_constant_perp_distance(self):
        """正对一堵平墙：欧氏距离随列增大，校正后的垂直距离保持一致。"""
        from fps.map import GameMap
        # 6×9 的窄厅，东墙 (x=5) 铺满整个视野，玩家站在正中
        rows = ["######", "#P..E#"] + ["#....#"] * 6 + ["######"]
        gmap = GameMap.from_rows(rows, "hall")
        player = Player(1.5, 4.5, 0.0)               # 面向东，东墙在 x=5
        tan_half = math.tan(player.fov * 0.5)
        raw, perp = [], []
        for x in range(0, 40, 4):
            cam = 2.0 * (x + 0.5) / 40 - 1.0
            ray_angle = player.angle + math.atan(cam * tan_half)
            hit = cast_ray(gmap, player.x, player.y, ray_angle)
            raw.append(hit.dist)
            perp.append(fisheye_correct(hit.dist, ray_angle - player.angle))
            self.assertEqual(hit.cell_x, 5)          # 每列都应命中同一堵东墙
        # 鱼眼效应：斜着量的距离边缘比中心长 0.5 格以上
        self.assertGreater(max(raw), min(raw) + 0.5)
        # 校正后：整堵墙保持「平」——垂直距离处处相等
        for value in perp:
            self.assertAlmostEqual(value, 3.5, places=6)


class TestTexture(unittest.TestCase):
    def test_texture_column_samples_by_wall_x(self):
        pattern = MATERIALS[1]["pattern"]
        width = len(pattern[0])
        self.assertEqual(texture_column(1, 0.0)[0], pattern[0][0])
        # 纹理列从上到下返回：末位对应纹理最后一行
        self.assertEqual(texture_column(1, 0.999999)[-1], pattern[-1][width - 1])
        mid = int(0.5 * width)
        column = texture_column(1, 0.5)
        self.assertEqual(column[0], pattern[0][mid])
        self.assertEqual(len(column), len(pattern))

    def test_sample_texel_rows(self):
        pattern = MATERIALS[2]["pattern"]
        height = len(pattern)
        self.assertEqual(sample_texel(2, 0.0, 0.0), int(pattern[0][0]))
        self.assertEqual(sample_texel(2, 0.0, 0.999), int(pattern[-1][0]))
        # 纵向采样应覆盖整张纹理
        seen = {sample_texel(1, 0.0, v / 12) for v in range(12)}
        self.assertGreater(len(seen), 1)

    def test_materials_registry(self):
        self.assertGreaterEqual(len(MATERIALS), 3)
        for key, spec in MATERIALS.items():
            pattern = spec["pattern"]
            width = len(pattern[0])
            self.assertTrue(all(len(row) == width for row in pattern),
                            f"材质 {key} 图案必须等宽")
            self.assertTrue(all(ch.isdigit() for row in pattern for ch in row))


class TestShading(unittest.TestCase):
    def test_dimmer_with_distance(self):
        levels = [int(SHADE_RAMP.index(shade_char(d, 0, 9)))
                  for d in (1, 3, 6, 10, 16, 24)]
        for a, b in zip(levels, levels[1:]):
            self.assertGreaterEqual(a, b, "距离越远应越暗")

    def test_side_wall_darker(self):
        for dist in (2.0, 6.0, 12.0):
            self.assertLess(SHADE_RAMP.index(shade_char(dist, 1, 9)),
                            SHADE_RAMP.index(shade_char(dist, 0, 9)))

    def test_output_always_in_ramp(self):
        for dist in (0.0, 0.5, 5.0, 40.0, 1000.0):
            for side in (0, 1):
                for lum in (0, 3, 6, 9):
                    ch = shade_char(dist, side, lum)
                    self.assertIn(ch, SHADE_RAMP)
        self.assertEqual(shade_char(0.0, 0, 0), " ")


class TestRenderWalls(unittest.TestCase):
    def test_renders_wall_band_and_returns_zbuf(self):
        gmap = load_map("crypt")
        player = Player(1.5, 1.5, math.pi / 2)       # 面向南
        buf = FrameBuffer(80, 24)
        view_h = 22
        zbuf = render_walls(gmap, player, buf, 80, view_h)
        self.assertEqual(len(zbuf), 80)
        for depth in zbuf:
            self.assertGreater(depth, 0.0)
            self.assertLessEqual(depth, MAX_DEPTH)
        # 地平线附近一定有墙，天花板区一定留空
        center = "".join(buf.get(x, view_h // 2) for x in range(80))
        self.assertNotIn(" ", center)
        top = "".join(buf.get(x, 0) for x in range(80))
        self.assertIn(" ", top)
        # 墙越高越近：近处列的墙带必须覆盖更多行
        covered = sum(1 for y in range(view_h) if buf.get(40, y) != " ")
        self.assertGreater(covered, 3)

    def test_render_survives_player_next_to_wall(self):
        gmap = load_map("crypt")
        player = Player(12.5, 9.5, math.pi)          # 贴墙看墙
        buf = FrameBuffer(40, 16)
        zbuf = render_walls(gmap, player, buf, 40, 14)
        self.assertTrue(all(0 < d < MAX_DEPTH for d in zbuf))


if __name__ == "__main__":
    unittest.main()
