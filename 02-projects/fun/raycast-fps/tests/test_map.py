"""map 测试：手工地图校验、非法地图拒绝、随机地图合法性、碰撞与视线。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.map import (GameMap, MapError, flood_reach, generate_random_map,
                     load_map, validate_rows)


class TestHandMaps(unittest.TestCase):
    def test_two_hand_maps_valid(self):
        for name in ("crypt", "vault"):
            gmap = load_map(name)
            with self.subTest(map=name):
                self.assertGreaterEqual(gmap.width, 10)
                # 边框全墙
                self.assertTrue(all(gmap.is_wall_cell(x, 0)
                                    for x in range(gmap.width)))
                self.assertTrue(all(gmap.is_wall_cell(x, gmap.height - 1)
                                    for x in range(gmap.width)))
                # 出生点/出口在地板上且连通
                self.assertFalse(gmap.is_wall_at(*gmap.spawn))
                self.assertFalse(gmap.is_wall_cell(*gmap.exit_cell))
                reach = flood_reach(gmap.grid,
                                    (math.floor(gmap.spawn[0]),
                                     math.floor(gmap.spawn[1])))
                self.assertIn(gmap.exit_cell, reach)
                self.assertGreaterEqual(len(gmap.enemy_spawns), 2)
                for x, y, _ in gmap.enemy_spawns + gmap.pickup_spawns:
                    self.assertIn((math.floor(x), math.floor(y)), reach)

    def test_entity_positions_are_cell_centers(self):
        gmap = load_map("crypt")
        for x, y, kind in gmap.enemy_spawns + gmap.pickup_spawns:
            self.assertAlmostEqual(x % 1, 0.5)
            self.assertAlmostEqual(y % 1, 0.5)
            self.assertIn(kind, ("patrol", "chaser", "ammo", "health"))


class TestValidation(unittest.TestCase):
    BASE = [
        "#####",
        "#P.E#",
        "#...#",
        "#...#",
        "#####",
    ]

    def test_valid_mini_map_passes(self):
        gmap = GameMap.from_rows(self.BASE, "mini")
        self.assertEqual(gmap.spawn, (1.5, 1.5))
        self.assertEqual(gmap.exit_cell, (3, 1))

    def test_bad_cases_rejected(self):
        cases = {
            "缺出生点": ["#####", "#..E#", "#...#", "#...#", "#####"],
            "两个出生点": ["#####", "#P.P#", "#.E.#", "#...#", "#####"],
            "缺出口": ["#####", "#P..#", "#...#", "#...#", "#####"],
            "开口边框": ["#####", "#P.E#", "#....", "#...#", "#####"],
            "非法字符": ["#####", "#P.E#", "#?..#", "#...#", "#####"],
            "行宽不齐": ["#####", "#P.E#", "#..", "#...#", "#####"],
            "空地图": [],
            # 左半区封死，出口隔在墙后，出生点走不到
            "出口不连通": ["#######", "#P#..E#", "#.#.#.#",
                        "#.#...#", "#######"],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(MapError):
                    GameMap.from_rows(rows, "bad")

    def test_validate_rows_error_messages(self):
        with self.assertRaisesRegex(MapError, "边框"):
            validate_rows(["#####", "#P.E#", "#....", "#...#", "#####"])
        with self.assertRaisesRegex(MapError, "P"):
            validate_rows(["#####", "#..E#", "#...#", "#...#", "#####"])


class TestRandomMaps(unittest.TestCase):
    def test_fifty_random_maps_all_legal_and_connected(self):
        for seed in range(50):
            gmap = generate_random_map(width=15, height=13, seed=seed,
                                       enemies=4, pickups=3)
            with self.subTest(seed=seed):
                self.assertTrue(all(gmap.is_wall_cell(x, 0)
                                    for x in range(gmap.width)))
                start = (math.floor(gmap.spawn[0]), math.floor(gmap.spawn[1]))
                reach = flood_reach(gmap.grid, start)
                self.assertIn(gmap.exit_cell, reach)
                self.assertEqual(len(gmap.enemy_spawns), 4)
                self.assertEqual(len(gmap.pickup_spawns), 3)
                for x, y, _ in gmap.enemy_spawns + gmap.pickup_spawns:
                    self.assertIn((math.floor(x), math.floor(y)), reach)

    def test_seed_is_reproducible(self):
        a = generate_random_map(seed=42)
        b = generate_random_map(seed=42)
        self.assertEqual(a.rows, b.rows)
        c = generate_random_map(seed=43)
        self.assertNotEqual(a.rows, c.rows)

    def test_random_map_has_at_least_three_wall_kinds(self):
        # 多抽几张，材质种类应当丰富起来
        kinds = set()
        for seed in range(10):
            gmap = generate_random_map(seed=seed, width=17, height=15)
            kinds.update(cell for row in gmap.grid for cell in row
                         if cell != 0)
        self.assertGreaterEqual(len(kinds), 3)


class TestCollision(unittest.TestCase):
    """圆 vs 网格：撞墙的轴被吃掉、贴墙滑动、永不穿墙。"""

    MAP = [
        "##########",
        "#P......E#",
        "#........#",
        "#........#",
        "#........#",
        "##########",
    ]

    def setUp(self):
        self.gmap = GameMap.from_rows(self.MAP, "room")

    def test_circle_detects_wall(self):
        self.assertTrue(self.gmap.circle_hits_wall(0.5, 2.5, 0.22))   # 墙格内
        self.assertFalse(self.gmap.circle_hits_wall(5.0, 2.5, 0.22))  # 地板中央
        # 半径压进左墙（墙面 x=1）也算
        self.assertTrue(self.gmap.circle_hits_wall(1.15, 2.5, 0.22))
        # 恰好相切不算碰撞
        self.assertFalse(self.gmap.circle_hits_wall(1.22, 2.5, 0.22))

    def test_four_directions_blocked_no_penetration(self):
        step = 0.3
        # (dx, dy, 撞到的墙面坐标, min/max 面)
        faces = ((1, 0, 9.0, "max"), (-1, 0, 1.0, "min"),
                 (0, -1, 1.0, "min"), (0, 1, 5.0, "max"))
        for dx, dy, face, side in faces:
            x, y = 5.0, 2.5
            for _ in range(50):
                x, y = self.gmap.try_move(x, y, dx * step, dy * step, 0.22)
                self.assertFalse(self.gmap.circle_hits_wall(x, y, 0.22),
                                 f"方向 ({dx},{dy}) 穿墙了")
            coord = x if dx else y
            if side == "min":
                # 不许进入安全线，且最终必须贴到安全线一步之内
                self.assertGreaterEqual(coord, face + 0.22 - 1e-9)
                self.assertLessEqual(coord, face + 0.22 + step + 1e-9)
            else:
                self.assertLessEqual(coord, face - 0.22 + 1e-9)
                self.assertGreaterEqual(coord, face - 0.22 - step - 1e-9)

    def test_sliding_along_wall_keeps_free_axis(self):
        """斜着撞墙：被挡的轴不动，另一轴继续走 = 贴墙滑动。"""
        x, y = 2.0, 1.5            # 靠近上墙（y=1 是地板行，y=0 是墙）
        nx, ny = self.gmap.try_move(x, y, 0.3, -0.3, 0.22)
        self.assertAlmostEqual(nx, 2.3, places=6)      # 横向照走
        self.assertAlmostEqual(ny, y, places=6)        # 向上被吃掉
        self.assertFalse(self.gmap.circle_hits_wall(nx, ny, 0.22))

    def test_diagonal_corner_never_penetrates(self):
        x, y = 1.5, 1.5            # 左上角
        for _ in range(30):
            x, y = self.gmap.try_move(x, y, -0.25, -0.25, 0.22)
            self.assertFalse(self.gmap.circle_hits_wall(x, y, 0.22))
            # 分轴步进停在角落一步之外，但绝不能压进安全线
            self.assertGreaterEqual(x, 1.22 - 1e-9)
            self.assertGreaterEqual(y, 1.22 - 1e-9)
            self.assertLessEqual(x, 1.5)
            self.assertLessEqual(y, 1.5)


class TestLineOfSight(unittest.TestCase):
    MAP = [
        "##########",
        "#P......E#",
        "#.######.#",
        "#........#",
        "##########",
    ]

    def setUp(self):
        self.gmap = GameMap.from_rows(self.MAP, "los")

    def test_open_corridor(self):
        self.assertTrue(self.gmap.segment_clear(1.5, 1.5, 8.5, 1.5))
        self.assertTrue(self.gmap.segment_clear(1.5, 3.5, 8.5, 3.5))

    def test_blocked_by_wall(self):
        # 从第 1 行看第 3 行，中间隔着第 2 行的横墙
        self.assertFalse(self.gmap.segment_clear(5.5, 1.5, 5.5, 3.5))
        # 斜穿墙角也不行
        self.assertFalse(self.gmap.segment_clear(2.5, 1.5, 2.5, 3.5))

    def test_open_ends_of_the_gap(self):
        # 墙两端的缺口 (1,2) 和 (8,2) 可以通视
        self.assertTrue(self.gmap.segment_clear(1.5, 1.5, 1.5, 3.5))
        self.assertTrue(self.gmap.segment_clear(8.5, 1.5, 8.5, 3.5))

    def test_degenerate_segment(self):
        self.assertTrue(self.gmap.segment_clear(5.5, 1.5, 5.5, 1.5))
        self.assertFalse(self.gmap.segment_clear(5.5, 2.5, 5.5, 2.5))


if __name__ == "__main__":
    unittest.main()
