"""sprites 测试：投影几何、画家排序、墙体遮挡、两类敌人 AI。

注意：地图必须过 ``from_rows`` 全套校验（P/E 各一个、边框封闭、实体可达），
所以本文件的迷你地图都带出生点与出口。
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.loop import FrameBuffer
from fps.map import GameMap, load_map
from fps.player import Player
from fps.sprites import (ENEMY_SPEC, SPRITE_ART, Enemy, Pickup, bfs_path,
                         project_sprite, render_sprites, sort_for_draw,
                         spawn_actors, update_enemies)

# 开敞房间 12×6：P 出生点在左上，E 出口在右上
ROOM = [
    "############",
    "#P........E#",
    "#..........#",
    "#..........#",
    "#..........#",
    "############",
]

# L 形走廊：上下两条横廊只靠右侧竖廊连通，横向上互相看不见
LCORRIDOR = [
    "############",
    "#P........E#",
    "#.########.#",
    "#.#......#.#",
    "#.#......#.#",
    "#.#......#.#",
    "#.###..###.#",
    "#..........#",
    "############",
]

# 遮挡测试用小地图：中排一堵墙隔开左右
OCC = [
    "############",
    "#P........E#",
    "#....#.....#",
    "#..........#",
    "#..........#",
    "############",
]


class TestProjection(unittest.TestCase):
    def setUp(self):
        self.player = Player(6.5, 4.0, 0.0)        # 面向东

    def test_sprite_ahead_is_centered(self):
        enemy = Enemy(9.5, 4.0, "patrol")
        proj = project_sprite(enemy, self.player, 80, 22)
        self.assertIsNotNone(proj)
        self.assertAlmostEqual(proj.screen_x, 40.0, places=6)
        self.assertAlmostEqual(proj.depth, 3.0, places=6)

    def test_farther_sprite_smaller(self):
        near = project_sprite(Enemy(8.5, 4.0, "patrol"), self.player, 80, 22)
        far = project_sprite(Enemy(8.5, 4.0, "patrol"),
                             Player(4.5, 4.0, 0.0), 80, 22)
        self.assertGreater(near.height_px, far.height_px)
        self.assertGreater(near.depth, 0.0)
        self.assertGreater(far.depth, near.depth)

    def test_off_center_sprite_offsets_screen_x(self):
        # 面向东时 +y 落在画面右侧，−y 落在左侧
        right = project_sprite(Enemy(8.0, 6.0, "patrol"), self.player, 80, 22)
        left = project_sprite(Enemy(8.0, 2.0, "patrol"), self.player, 80, 22)
        self.assertGreater(right.screen_x, 40.0)
        self.assertLess(left.screen_x, 40.0)

    def test_sprite_behind_player_is_none(self):
        behind = Enemy(2.0, 4.0, "patrol")
        self.assertIsNone(project_sprite(behind, self.player, 80, 22))

    def test_sprite_sits_on_floor_line(self):
        enemy = Enemy(8.5, 4.0, "patrol")
        proj = project_sprite(enemy, self.player, 80, 22)
        wall_h = 22.0 / proj.depth
        self.assertAlmostEqual(proj.bottom, 11.0 + wall_h / 2, places=6)
        self.assertLess(proj.top, proj.bottom)

    def test_pickup_is_shorter_than_enemy(self):
        enemy = project_sprite(Enemy(8.5, 4.0, "patrol"), self.player, 80, 22)
        box = project_sprite(Pickup(8.5, 4.0, "ammo"), self.player, 80, 22)
        self.assertLess(box.height_px, enemy.height_px)


class TestPainterAndOcclusion(unittest.TestCase):
    @staticmethod
    def _scene_with_wall(depth: float):
        """(player, zbuf)：zbuf 全部置为 depth，模拟一堵距离 depth 的墙。"""
        player = Player(3.5, 2.5, 0.0)            # 面向东
        zbuf = [depth] * 40
        return player, zbuf

    def test_sort_far_to_near(self):
        player = Player(5.0, 5.0, 0.0)
        near = Pickup(6.0, 5.0, "ammo")
        mid = Enemy(7.0, 5.0, "patrol")
        far = Enemy(10.0, 5.0, "chaser")
        order = sort_for_draw([near, mid, far], player)
        self.assertEqual([id(a) for a in order],
                         [id(far), id(mid), id(near)])
        far.alive = False                          # 死的不参与绘制
        self.assertEqual(len(sort_for_draw([near, mid, far], player)), 2)

    def test_wall_column_blocks_sprite(self):
        """精灵深度 6 > 墙距 3：整只被 z-buffer 挡掉。"""
        player, zbuf = self._scene_with_wall(3.0)
        buf = FrameBuffer(40, 16)
        enemy = Enemy(9.5, 3.5, "patrol")
        render_sprites([enemy], player, zbuf, buf, 40, 14)
        drawn = [buf.get(x, y) for y in range(14) for x in range(40)]
        self.assertEqual([ch for ch in drawn if ch != " "], [])

    def test_close_wall_still_shows_sprite(self):
        """墙距 9 > 精灵深度 6：精灵正常画出。"""
        player, zbuf = self._scene_with_wall(9.0)
        buf = FrameBuffer(40, 16)
        enemy = Enemy(7.5, 2.5, "patrol")
        render_sprites([enemy], player, zbuf, buf, 40, 14)
        drawn = [buf.get(x, y) for y in range(14) for x in range(40)]
        self.assertTrue(any(ch != " " for ch in drawn))

    def test_partial_columns_occluded_independently(self):
        """z-buffer 是逐列生效的：左半有近墙，精灵只许出现在右半。"""
        player, zbuf = self._scene_with_wall(99.0)   # 默认全露出
        for x in range(20):
            zbuf[x] = 1.0                            # 左半放一堵近墙
        buf = FrameBuffer(40, 16)
        enemy = Enemy(7.5, 2.5, "patrol")
        render_sprites([enemy], player, zbuf, buf, 40, 14)
        cols = {x for y in range(14) for x in range(40)
                if buf.get(x, y) != " "}
        self.assertTrue(cols)
        self.assertTrue(all(x >= 20 for x in cols))


class TestPatrolAI(unittest.TestCase):
    """把巡逻型的视线距离关掉 = 强制纯巡逻，不被追击 AI 干扰。"""

    def setUp(self):
        self.gmap = GameMap.from_rows(ROOM, "room")
        self.player = Player(6.5, 3.0, 0.0)
        self._sight = ENEMY_SPEC["patrol"]["sight"]
        ENEMY_SPEC["patrol"]["sight"] = 0.0
        self.addCleanup(ENEMY_SPEC["patrol"].__setitem__, "sight", self._sight)

    def test_patrol_bounces_off_wall(self):
        enemy = Enemy(2.0, 3.0, "patrol")           # dir 0 = 向东
        start_x = enemy.x
        seen_dirs = {enemy.dir_idx}
        reached_far = False
        for _ in range(400):
            enemy.update(self.gmap, self.player, 1 / 30)
            seen_dirs.add(enemy.dir_idx)
            self.assertFalse(self.gmap.circle_hits_wall(
                enemy.x, enemy.y, enemy.radius))
            if enemy.x > 9.0:
                reached_far = True
        self.assertTrue(reached_far, "应先沿走廊向东走出一大段")
        self.assertGreater(enemy.x, start_x)
        self.assertGreater(len(seen_dirs), 1, "撞墙后必须换过方向")
        # 长期巡逻也不许越出地板区（x: 1..11, y: 1..5）
        self.assertTrue(1.0 + enemy.radius - 1e-6 <= enemy.x
                        <= 11.0 - enemy.radius + 1e-6)
        self.assertTrue(1.0 + enemy.radius - 1e-6 <= enemy.y
                        <= 5.0 - enemy.radius + 1e-6)

    def test_patrol_stays_inside(self):
        enemy = Enemy(2.0, 2.0, "patrol")
        for _ in range(300):
            enemy.update(self.gmap, self.player, 1 / 30)
            self.assertFalse(self.gmap.circle_hits_wall(
                enemy.x, enemy.y, enemy.radius))


class TestChaserAI(unittest.TestCase):
    def test_chaser_closes_distance_with_los(self):
        gmap = GameMap.from_rows(ROOM, "room")
        player = Player(8.5, 3.0, math.pi)
        enemy = Enemy(2.5, 3.0, "chaser")
        before = math.hypot(enemy.x - player.x, enemy.y - player.y)
        for _ in range(90):
            enemy.update(gmap, player, 1 / 30)
        after = math.hypot(enemy.x - player.x, enemy.y - player.y)
        self.assertLess(after, before - 1.0, "看得见就该扑上来")
        self.assertFalse(gmap.circle_hits_wall(enemy.x, enemy.y,
                                               enemy.radius))

    def test_chaser_paths_around_corner(self):
        """隔着 L 形墙看不到，也要绕路逼近（BFS 找路）。"""
        gmap = GameMap.from_rows(LCORRIDOR, "L")
        player = Player(9.5, 7.5, math.pi)             # 下排右端
        enemy = Enemy(9.5, 1.5, "chaser")              # 上排右端
        enemy.aggro = 999.0                            # 一开始就咬死目标
        self.assertFalse(gmap.segment_clear(enemy.x, enemy.y,
                                            player.x, player.y))
        before = math.hypot(enemy.x - player.x, enemy.y - player.y)
        for _ in range(600):
            enemy.update(gmap, player, 1 / 30)
        after = math.hypot(enemy.x - player.x, enemy.y - player.y)
        self.assertLess(after, before - 2.0, "应绕过隔墙明显接近")
        self.assertFalse(gmap.circle_hits_wall(enemy.x, enemy.y,
                                               enemy.radius))

    def test_bfs_path_is_valid_steps(self):
        gmap = GameMap.from_rows(LCORRIDOR, "L")
        path = bfs_path(gmap, (1, 1), (9, 7))
        self.assertTrue(path)
        self.assertEqual(path[-1], (9, 7))
        prev = (1, 1)
        for cell in path:
            self.assertEqual(abs(cell[0] - prev[0])
                             + abs(cell[1] - prev[1]), 1)
            self.assertFalse(gmap.is_wall_cell(*cell))
            prev = cell

    def test_bfs_path_rejects_wall_goal(self):
        gmap = GameMap.from_rows(LCORRIDOR, "L")
        self.assertEqual(bfs_path(gmap, (1, 1), (5, 2)), [])   # 墙格
        self.assertEqual(bfs_path(gmap, (1, 1), (1, 1)), [])   # 原地

    def test_enemy_attack_event_when_adjacent(self):
        gmap = GameMap.from_rows(ROOM, "room")
        player = Player(5.5, 3.0, 0.0)
        enemy = Enemy(5.9, 3.0, "chaser")              # 贴脸
        enemy.cooldown = 0.0
        events = enemy.update(gmap, player, 1 / 30)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "attack")
        self.assertGreater(events[0][1], 0)
        self.assertGreater(enemy.cooldown, 0)           # 进入冷却
        self.assertEqual(enemy.update(gmap, player, 1 / 30), [])  # 冷却中

    def test_hurt_marks_aggro_and_death(self):
        enemy = Enemy(2.0, 2.0, "patrol")
        self.assertEqual(enemy.aggro, 0.0)
        self.assertFalse(enemy.hurt(10))                # 50 血剩 40
        self.assertEqual(enemy.hp, 40)
        self.assertGreater(enemy.aggro, 100)            # 记仇
        self.assertTrue(enemy.hurt(100))                # 致死
        self.assertFalse(enemy.alive)
        self.assertEqual(enemy.hp, 0)
        self.assertFalse(enemy.hurt(10))                # 死了不再吃伤害


class TestSpritesRegistry(unittest.TestCase):
    def test_two_enemies_and_pickups_defined(self):
        self.assertIn("patrol", SPRITE_ART)
        self.assertIn("chaser", SPRITE_ART)
        self.assertIn("ammo", SPRITE_ART)
        self.assertIn("health", SPRITE_ART)
        for name, art in SPRITE_ART.items():
            width = len(art[0])
            self.assertTrue(all(len(row) == width for row in art),
                            f"精灵 {name} 图案必须等宽")
            for row in art:
                for cell in row:
                    self.assertTrue(cell is None or cell.isdigit())

    def test_spawn_actors_from_map(self):
        gmap = load_map("vault")
        enemies, pickups = spawn_actors(gmap)
        self.assertEqual(len(enemies), len(gmap.enemy_spawns))
        self.assertEqual(len(pickups), len(gmap.pickup_spawns))
        self.assertEqual({e.kind for e in enemies}, {"patrol", "chaser"})
        self.assertGreaterEqual({p.kind for p in pickups},
                                {"ammo", "health"} & {p.kind for p in pickups})
        self.assertTrue(pickups)

    def test_update_enemies_aggregates_events(self):
        gmap = GameMap.from_rows(ROOM, "room")
        player = Player(5.5, 3.0, 0.0)
        enemies = [Enemy(5.9, 3.0, "chaser"), Enemy(2.0, 2.0, "patrol")]
        events = update_enemies(enemies, gmap, player, 1 / 30)
        self.assertEqual(len(events), 1)                # 只有贴脸那只出手
        self.assertEqual(events[0][2], enemies[0])


if __name__ == "__main__":
    unittest.main()
