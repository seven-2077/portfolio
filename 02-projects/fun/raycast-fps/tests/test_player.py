"""player 测试：移动/转向、按键翻译、开局朝向、小地图结构。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.map import GameMap, load_map
from fps.player import (MOVE_SPEED, PLAYER_RADIUS, TURN_SPEED, KeyReader,
                        Player, choose_start_angle, keys_to_actions,
                        render_minimap)
from fps.sprites import Enemy, Pickup

ROOM = [
    "##########",
    "#P......E#",
    "#........#",
    "#........#",
    "#........#",
    "##########",
]


class TestMovement(unittest.TestCase):
    def setUp(self):
        self.gmap = GameMap.from_rows(ROOM, "room")
        self.player = Player(5.0, 2.5, 0.0)      # 面向东

    def test_forward_moves_along_facing(self):
        self.player.update({"forward"}, 0.5, self.gmap)
        self.assertAlmostEqual(self.player.x, 5.0 + MOVE_SPEED * 0.5)
        self.assertAlmostEqual(self.player.y, 2.5)

    def test_back_moves_backward(self):
        self.player.update({"back"}, 0.5, self.gmap)
        self.assertAlmostEqual(self.player.x, 5.0 - MOVE_SPEED * 0.5)

    def test_strafe_is_perpendicular(self):
        self.player.update({"strafe_r"}, 0.5, self.gmap)   # 面向东 → 向 +y
        self.assertAlmostEqual(self.player.x, 5.0)
        self.assertAlmostEqual(self.player.y, 2.5 + MOVE_SPEED * 0.5)

    def test_forward_plus_strafe_keeps_constant_speed(self):
        self.player.update({"forward", "strafe_r"}, 1.0, self.gmap)
        moved = math.hypot(self.player.x - 5.0, self.player.y - 2.5)
        self.assertAlmostEqual(moved, MOVE_SPEED, places=6)

    def test_turn_changes_angle_at_turn_speed(self):
        self.player.update({"turn_r"}, 0.5, self.gmap)
        self.assertAlmostEqual(self.player.angle, TURN_SPEED * 0.5, places=6)
        self.player.update({"turn_l"}, 1.0, self.gmap)
        self.assertAlmostEqual(self.player.angle, -TURN_SPEED * 0.5, places=6)

    def test_angle_stays_normalized(self):
        for _ in range(40):
            self.player.update({"turn_r"}, 0.5, self.gmap)
        self.assertGreaterEqual(self.player.angle, -math.pi)
        self.assertLess(self.player.angle, math.pi)

    def test_blocked_by_wall_no_penetration(self):
        self.player.angle = 0.0                     # 朝东，x=9 是墙
        for _ in range(60):
            self.player.update({"forward"}, 1 / 30, self.gmap)
            self.assertFalse(self.gmap.circle_hits_wall(
                self.player.x, self.player.y, self.player.radius))
        self.assertLess(self.player.x, 8.78 + 1e-9)
        self.assertGreater(self.player.x, 7.5)      # 确实走到了墙边

    def test_player_radius_constant(self):
        self.assertGreater(PLAYER_RADIUS, 0)
        self.assertLess(PLAYER_RADIUS, 0.5)


class TestStartAngle(unittest.TestCase):
    def test_picks_open_direction(self):
        gmap = load_map("crypt")
        angle = choose_start_angle(gmap, *gmap.spawn)
        # 开局方向必须能看出去一段距离（不贴脸怼墙）
        from fps.raycaster import cast_ray
        self.assertGreater(cast_ray(gmap, gmap.spawn[0], gmap.spawn[1],
                                    angle).dist, 2.0)


class TestKeys(unittest.TestCase):
    def test_wasd_and_turn_keys(self):
        self.assertEqual(keys_to_actions(["w"]), {"forward"})
        self.assertEqual(keys_to_actions(["s"]), {"back"})
        self.assertEqual(keys_to_actions(["a"]), {"strafe_l"})
        self.assertEqual(keys_to_actions(["d"]), {"strafe_r"})
        self.assertEqual(keys_to_actions(["j"]), {"turn_l"})
        self.assertEqual(keys_to_actions(["l"]), {"turn_r"})
        self.assertEqual(keys_to_actions([" "]), {"shoot"})
        self.assertEqual(keys_to_actions(["m"]), {"toggle_map"})
        self.assertEqual(keys_to_actions(["q"]), {"quit"})

    def test_arrow_keys_with_prefix(self):
        # msvcrt 方向键 = \x00 或 \xe0 + 码
        self.assertEqual(keys_to_actions(["\x00", "K"]), {"turn_l"})
        self.assertEqual(keys_to_actions(["\xe0", "M"]), {"turn_r"})
        self.assertEqual(keys_to_actions(["\x00", "H"]), {"forward"})
        self.assertEqual(keys_to_actions(["\xe0", "P"]), {"back"})

    def test_mixed_sequence_and_unknown_keys(self):
        actions = keys_to_actions(["w", "w", "\x00", "M", "z", " ", "!"])
        self.assertEqual(actions, {"forward", "turn_r", "shoot"})

    def test_truncated_arrow_prefix_is_safe(self):
        self.assertEqual(keys_to_actions(["\x00"]), set())
        self.assertEqual(keys_to_actions(["\x00", "Z"]), set())


class TestKeyReader(unittest.TestCase):
    def test_poll_consumes_buffer_until_empty(self):
        stream = iter(["w", "\x00", "M", None])
        reader = KeyReader(read_char=lambda: next(stream, None))
        self.assertEqual(reader.poll(), {"forward", "turn_r"})

    def test_poll_empty_buffer(self):
        reader = KeyReader(read_char=lambda: None)
        self.assertEqual(reader.poll(), set())

    def test_poll_respects_max_keys(self):
        calls = []

        def read():
            calls.append(1)
            return "w"

        KeyReader(read_char=read).poll(max_keys=5)
        self.assertEqual(len(calls), 5)


class TestMinimap(unittest.TestCase):
    def setUp(self):
        self.gmap = load_map("crypt")
        self.player = Player(*self.gmap.spawn)

    def test_structure_and_markers(self):
        # 开大窗口盖住整张 crypt，并把实体交给小地图画出来
        enemies = [Enemy(x, y, kind)
                   for x, y, kind in self.gmap.enemy_spawns]
        pickups = [Pickup(x, y, kind)
                   for x, y, kind in self.gmap.pickup_spawns]
        rows = render_minimap(self.gmap, self.player, enemies, pickups,
                              width=33, height=31)
        self.assertEqual(len(rows), 31)
        self.assertTrue(all(len(row) == 33 for row in rows))
        joined = "".join(rows)
        self.assertIn("@", joined)          # 玩家
        self.assertIn("#", joined)          # 墙
        self.assertIn("E", joined)          # 出口
        self.assertIn("X", joined)          # 敌人
        self.assertIn("+", joined)          # 拾取物

    def test_player_marker_at_window_center(self):
        rows = render_minimap(self.gmap, self.player, width=15, height=9)
        self.assertEqual(rows[4][7], "@")   # 出生点 (1,1) 未被窗口裁掉时

    def test_dead_enemy_hidden(self):
        from fps.sprites import Enemy
        enemy = Enemy(*self.gmap.enemy_spawns[0])
        enemy.alive = False
        rows = render_minimap(self.gmap, self.player, [enemy],
                              width=31, height=21)
        self.assertNotIn("X", "".join(rows))
        enemy.alive = True
        rows = render_minimap(self.gmap, self.player, [enemy],
                              width=31, height=21)
        self.assertIn("X", "".join(rows))


if __name__ == "__main__":
    unittest.main()
