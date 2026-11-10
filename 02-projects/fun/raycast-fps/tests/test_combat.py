"""combat 测试：hitscan 命中 / 隔墙失效、弹药、拾取、出口、胜负判定。"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.combat import (AIM_TOLERANCE, EXIT_BONUS_SCORE, WEAPON_DAMAGE,
                        angle_delta, check_end, check_exit, collect_pickups,
                        damage_player, try_shoot)
from fps.loop import Game
from fps.map import GameMap
from fps.player import Player
from fps.sprites import Enemy, Pickup

# 开敞房间：正东方向一路畅通到墙
OPEN = [
    "############",
    "#P........E#",
    "#..........#",
    "#..........#",
    "#..........#",
    "############",
]

# L 形走廊：站在下排朝北开枪，正北半格外就是墙，敌人却在上排
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


def make_game(rows, px=2.5, py=3.0, angle=0.0):
    """建一局并把玩家摆到指定位置与朝向（angle 0 = 正东）。"""
    game = Game(GameMap.from_rows(rows, "combat"))
    game.player.x, game.player.y, game.player.angle = px, py, angle
    return game


class TestHitscan(unittest.TestCase):
    def test_hit_reduces_hp_and_ammo(self):
        game = make_game(OPEN)
        enemy = Enemy(6.5, 3.0, "patrol")           # 正东 4 格，射程内
        game.enemies = [enemy]
        kind, target = try_shoot(game)
        self.assertEqual(kind, "hit")
        self.assertIs(target, enemy)
        self.assertEqual(enemy.hp, 50 - WEAPON_DAMAGE)
        self.assertEqual(game.player.ammo, 23)       # 24 − 1
        self.assertEqual(game.player.score, 0)       # 没死没分

    def test_kill_awards_score(self):
        game = make_game(OPEN)
        enemy = Enemy(6.5, 3.0, "patrol")
        enemy.hp = 30                                # 一枪致命的血量
        game.enemies = [enemy]
        kind, target = try_shoot(game)
        self.assertEqual(kind, "kill")
        self.assertIs(target, enemy)
        self.assertFalse(enemy.alive)
        self.assertEqual(game.player.score, enemy.score_value)
        # 尸体不再吃第二枪
        self.assertEqual(try_shoot(game)[0], "miss")

    def test_nearest_target_wins(self):
        game = make_game(OPEN)
        near = Enemy(4.5, 3.0, "patrol")
        far = Enemy(8.5, 3.0, "chaser")
        game.enemies = [far, near]                  # 乱序放，照样选最近
        kind, target = try_shoot(game)
        self.assertEqual(kind, "hit")
        self.assertIs(target, near)
        self.assertEqual(far.hp, 100)               # 远的没挨打

    def test_miss_when_no_target_in_line(self):
        game = make_game(OPEN, angle=math.pi / 2)   # 朝北开枪，正北没人
        game.enemies = [Enemy(6.5, 3.0, "patrol")]
        kind, target = try_shoot(game)
        self.assertEqual(kind, "miss")
        self.assertIsNone(target)
        self.assertEqual(game.player.ammo, 23)      # 打空也耗弹

    def test_aim_tolerance_edge(self):
        # 4 格外横偏 0.3：角位移 0.0749 ≤ 角半径 0.0749 + 容差 → 命中
        game = make_game(OPEN)
        enemy = Enemy(6.5, 3.3, "patrol")
        game.enemies = [enemy]
        self.assertEqual(try_shoot(game)[0], "hit")

        # 4 格外横偏 1.0：0.245 > 0.1049 → 打飞
        game = make_game(OPEN)
        enemy = Enemy(6.5, 4.0, "patrol")
        game.enemies = [enemy]
        self.assertEqual(try_shoot(game)[0], "miss")

    def test_wall_blocks_shot(self):
        """敌人在正北方向但隔了一堵墙：射线半格即撞墙，够不着。"""
        game = make_game(LCORRIDOR, px=9.5, py=7.5, angle=-math.pi / 2)
        enemy = Enemy(9.5, 1.5, "chaser")           # 上排，隔墙正对准星
        game.enemies = [enemy]
        self.assertGreater(math.hypot(enemy.x - game.player.x,
                                      enemy.y - game.player.y), 3.0)
        kind, target = try_shoot(game)
        self.assertEqual(kind, "miss")
        self.assertIsNone(target)
        self.assertEqual(enemy.hp, 100)             # 一滴血没掉
        self.assertEqual(game.player.ammo, 23)

    def test_no_ammo_refuses_to_fire(self):
        game = make_game(OPEN)
        game.enemies = [Enemy(6.5, 3.0, "patrol")]
        game.player.ammo = 0
        kind, target = try_shoot(game)
        self.assertEqual(kind, "no_ammo")
        self.assertIsNone(target)
        self.assertEqual(game.player.ammo, 0)
        self.assertTrue(game.messages)              # 有提示

    def test_shot_wakes_nearby_enemies(self):
        game = make_game(OPEN)
        near = Enemy(6.5, 3.0, "patrol")
        far = Enemy(10.5, 4.5, "chaser")            # 约 8.1 格，枪声范围 9
        game.enemies = [near, far]
        try_shoot(game)
        self.assertGreater(near.aggro, 0.0)
        self.assertGreater(far.aggro, 0.0)


class TestAngleDelta(unittest.TestCase):
    def test_wraps_around(self):
        self.assertAlmostEqual(angle_delta(math.pi - 0.1, -math.pi + 0.1),
                               -0.2)
        self.assertAlmostEqual(angle_delta(0.0, math.tau), 0.0)
        self.assertAlmostEqual(angle_delta(-1.0, 1.0), -2.0)
        self.assertAlmostEqual(angle_delta(0.5, 0.5), 0.0)

    def test_constants(self):
        self.assertGreater(WEAPON_DAMAGE, 0)
        self.assertGreaterEqual(AIM_TOLERANCE, 0.0)
        self.assertEqual(EXIT_BONUS_SCORE, 50)


class TestDamageAndPickups(unittest.TestCase):
    def test_damage_player_reduces_hp(self):
        game = make_game(OPEN)
        damage_player(game, 8)
        self.assertEqual(game.player.hp, 92)
        self.assertTrue(game.player.alive)
        self.assertTrue(any("被攻击" in m for m, _ in game.messages))

    def test_damage_to_zero_kills(self):
        game = make_game(OPEN)
        damage_player(game, 999)
        self.assertEqual(game.player.hp, 0)
        self.assertFalse(game.player.alive)
        self.assertTrue(any("倒下" in m for m, _ in game.messages))

    def test_pickup_ammo_and_score(self):
        game = make_game(OPEN, 2.5, 2.5)
        box = Pickup(2.6, 2.5, "ammo")
        far = Pickup(7.5, 4.5, "health")
        game.pickups = [box, far]
        messages = collect_pickups(game)
        self.assertEqual(len(messages), 1)          # 远的没捡到
        self.assertEqual(game.player.ammo, 24 + 12)
        self.assertEqual(game.player.score, 10)
        self.assertTrue(box.taken)
        self.assertFalse(far.taken)
        self.assertEqual(collect_pickups(game), [])  # 已拾取不重复生效

    def test_pickup_health_caps_at_100(self):
        game = make_game(OPEN, 2.5, 2.5)
        game.player.hp = 50
        game.pickups = [Pickup(2.5, 2.5, "health")]
        messages = collect_pickups(game)
        self.assertEqual(game.player.hp, 80)
        self.assertIn("医疗包", messages[0])
        game.player.hp = 90
        game.pickups = [Pickup(2.5, 2.5, "health")]
        collect_pickups(game)
        self.assertEqual(game.player.hp, 100)       # 不超过上限


class TestExitAndOutcome(unittest.TestCase):
    def test_exit_bonus_once(self):
        game = make_game(OPEN, px=10.5, py=1.5)     # 踏上出口格
        message = check_exit(game)
        self.assertIsNotNone(message)
        self.assertTrue(game.exit_taken)
        self.assertEqual(game.player.score, EXIT_BONUS_SCORE)
        self.assertIsNone(check_exit(game))          # 只奖励一次
        self.assertEqual(game.player.score, EXIT_BONUS_SCORE)

    def test_exit_not_granted_elsewhere(self):
        game = make_game(OPEN, 2.5, 2.5)
        self.assertIsNone(check_exit(game))
        self.assertFalse(game.exit_taken)
        self.assertEqual(game.player.score, 0)

    def test_ongoing_game_has_no_outcome(self):
        game = make_game(OPEN)
        game.enemies = [Enemy(6.5, 3.0, "patrol")]
        self.assertIsNone(check_end(game))

    def test_win_when_all_enemies_dead(self):
        game = make_game(OPEN)
        enemy = Enemy(6.5, 3.0, "patrol")
        game.enemies = [enemy]
        enemy.hurt(999)
        self.assertEqual(check_end(game), "win")

    def test_lose_when_player_dies(self):
        game = make_game(OPEN)
        game.enemies = [Enemy(6.5, 3.0, "patrol")]  # 敌人还活着也一样输
        game.player.take_damage(999)
        self.assertEqual(check_end(game), "lose")

    def test_empty_map_is_not_auto_win(self):
        game = make_game(OPEN)                       # 地图没放敌人
        self.assertIsNone(check_end(game))


if __name__ == "__main__":
    unittest.main()
