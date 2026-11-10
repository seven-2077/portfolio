"""loop 测试：帧缓冲结构、预录输入、单帧流程、draw 画面与 run 统计。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fps.loop import FrameBuffer, Game, ScriptedInput, make_game, run
from fps.map import GameMap
from fps.sprites import Enemy

OPEN = [
    "############",
    "#P........E#",
    "#..........#",
    "#..........#",
    "#..........#",
    "############",
]


def make_open_game():
    return Game(GameMap.from_rows(OPEN, "loop"))


class TestFrameBuffer(unittest.TestCase):
    def test_dimensions_and_default_fill(self):
        buf = FrameBuffer(10, 4)
        self.assertEqual((buf.width, buf.height), (10, 4))
        self.assertEqual(len(buf.cells), 4)
        self.assertTrue(all(ch == " " for row in buf.cells for ch in row))

    def test_put_get_bounds(self):
        buf = FrameBuffer(5, 3)
        buf.put(2, 1, "A")
        self.assertEqual(buf.get(2, 1), "A")
        buf.put(0, 0, "multi")                       # 多字符只留第一个
        self.assertEqual(buf.get(0, 0), "m")
        for x, y in [(-1, 0), (5, 0), (0, 3), (0, -1)]:   # 越界静默忽略
            buf.put(x, y, "X")
        self.assertEqual(buf.get(-1, 0), "")
        self.assertEqual(buf.get(99, 99), "")
        self.assertEqual(buf.get(0, 1), " ")

    def test_write_text_clips_at_edge(self):
        buf = FrameBuffer(6, 2)
        buf.write_text(3, 0, "ABCDE")
        self.assertEqual("".join(buf.cells[0]), "   ABC")
        self.assertEqual("".join(buf.cells[1]), "      ")

    def test_overlay_row_pads_and_truncates(self):
        buf = FrameBuffer(6, 2)
        buf.overlay_row(0, "hi")
        self.assertEqual("".join(buf.cells[0]), "hi    ")
        buf.overlay_row(0, "123456789")
        self.assertEqual("".join(buf.cells[0]), "123456")
        buf.overlay_row(9, "x")                      # 越界不抛异常
        buf.overlay_row(-1, "x")

    def test_clear_resets_to_fill(self):
        buf = FrameBuffer(4, 2)
        buf.put(1, 1, "#")
        buf.clear()
        self.assertTrue(all(ch == " " for row in buf.cells for ch in row))
        buf.clear("#")
        self.assertTrue(all(ch == "#" for row in buf.cells for ch in row))

    def test_render_structure(self):
        buf = FrameBuffer(4, 3)
        buf.write_text(0, 1, "ab")
        frame = buf.render()
        lines = frame.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(len(line) == 4 for line in lines))
        self.assertEqual(lines[1], "ab  ")
        self.assertNotIn("\x1b", frame)              # 纯文本，转义在 run 里


class TestScriptedInput(unittest.TestCase):
    def test_frame_budget_per_entry(self):
        src = ScriptedInput([({"forward"}, 2), ({"turn_r"}, 1)],
                            quit_when_done=True)
        self.assertEqual(src.poll(), {"forward"})
        self.assertEqual(src.poll(), {"forward"})     # 第 2 帧后条目耗尽
        self.assertEqual(src.poll(), {"turn_r"})      # 只给 1 帧
        self.assertEqual(src.poll(), {"quit"})        # 脚本走完自动退出

    def test_no_auto_quit(self):
        src = ScriptedInput([({"forward"}, 1)])
        self.assertEqual(src.poll(), {"forward"})
        self.assertEqual(src.poll(), set())

    def test_poll_returns_copies(self):
        actions = {"forward"}
        src = ScriptedInput([(actions, 5)])
        got = src.poll()
        got.add("shoot")                              # 污染返回值不影响脚本
        self.assertEqual(src.poll(), {"forward"})


class TestGameStep(unittest.TestCase):
    def setUp(self):
        self.game = make_open_game()

    def test_toggle_map(self):
        self.assertTrue(self.game.show_minimap)
        self.game.step({"toggle_map"}, 1 / 30)
        self.assertFalse(self.game.show_minimap)
        self.game.step({"toggle_map"}, 1 / 30)
        self.assertTrue(self.game.show_minimap)

    def test_status_freezes_world(self):
        self.game.status = "win"
        x0, y0 = self.game.player.x, self.game.player.y
        self.game.step({"forward"}, 1 / 30)
        self.assertEqual((self.game.player.x, self.game.player.y), (x0, y0))

    def test_fire_cooldown_limits_rate(self):
        self.assertEqual(self.game.player.ammo, 24)
        self.game.step({"shoot"}, 1 / 30)             # 第一枪
        self.assertEqual(self.game.player.ammo, 23)
        self.game.step({"shoot"}, 1 / 30)             # 冷却中，压枪
        self.assertEqual(self.game.player.ammo, 23)
        self.game.step({"shoot"}, 0.3)                # 冷却结束，再来一枪
        self.assertEqual(self.game.player.ammo, 22)

    def test_enemy_attack_hurts_player(self):
        self.game.player.x, self.game.player.y = 5.5, 3.0
        self.game.enemies = [Enemy(5.9, 3.0, "chaser")]
        self.game.step(set(), 1 / 30)
        self.assertEqual(self.game.player.hp, 92)     # 一击 8 点
        self.game.step(set(), 1 / 30)                 # 攻击冷却中
        self.assertEqual(self.game.player.hp, 92)

    def test_lose_on_death(self):
        self.game.player.take_damage(999)
        self.game.step(set(), 1 / 30)
        self.assertEqual(self.game.status, "lose")
        self.assertTrue(any("血量归零" in m for m, _ in self.game.messages))

    def test_win_when_last_enemy_falls(self):
        enemy = Enemy(6.5, 3.0, "patrol")
        enemy.hurt(999)
        self.game.enemies = [enemy]
        self.game.step(set(), 1 / 30)
        self.assertEqual(self.game.status, "win")
        self.assertTrue(any("通关" in m for m, _ in self.game.messages))

    def test_messages_expire(self):
        self.game.push("hello", 0.05)
        self.assertTrue(self.game.messages)
        self.game.step(set(), 0.1)
        self.assertEqual(self.game.messages, [])

    def test_frames_counter(self):
        for _ in range(3):
            self.game.step(set(), 1 / 30)
        self.assertEqual(self.game.frames, 3)


class TestGameDraw(unittest.TestCase):
    def setUp(self):
        self.game = make_open_game()

    def test_frame_structure(self):
        lines = self.game.draw().split("\n")
        self.assertEqual(len(lines), 24)
        self.assertTrue(all(len(line) == 80 for line in lines))

    def test_crosshair_at_center(self):
        lines = self.game.draw().split("\n")
        self.assertEqual(lines[11][40], "+")

    def test_hud_shows_vitals(self):
        lines = self.game.draw().split("\n")
        hud = lines[22]
        self.assertIn("HP[", hud)
        self.assertIn("AMMO", hud)
        self.assertIn("SCORE", hud)
        self.assertIn("FPS", hud)
        self.assertIn("[WASD]", lines[23])

    def test_minimap_overlay_toggle(self):
        on_lines = self.game.draw().split("\n")
        # 小地图窗口中心（玩家格）落在偏移 (1,1) 后的 (9,5)
        self.assertEqual(on_lines[5][9], "@")
        self.game.show_minimap = False
        off = self.game.draw()
        self.assertNotEqual("\n".join(on_lines), off)

    def test_win_banner_replaces_hint(self):
        self.game.status = "win"
        self.game.player.score = 123
        lines = self.game.draw().split("\n")
        self.assertIn("通关", lines[23])


class TestRunLoop(unittest.TestCase):
    def test_run_stats_and_callback(self):
        game = make_open_game()
        source = ScriptedInput([({"forward"}, 3)], quit_when_done=True)
        seen = []
        stats = run(game, input_source=source, target_fps=30,
                    show=False, realtime=False,
                    on_frame=lambda i, frame: seen.append((i, frame)))
        self.assertEqual(stats["frames"], 3.0)
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0][0], 0)
        self.assertIn("\n", seen[0][1])               # 回调拿到完整帧
        self.assertGreater(stats["fps"], 0.0)
        self.assertIsNone(game.status)

    def test_run_respects_max_frames(self):
        game = make_open_game()
        source = ScriptedInput([({"forward"}, 100000)])
        stats = run(game, input_source=source, target_fps=30,
                    show=False, realtime=False, max_frames=10)
        self.assertEqual(stats["frames"], 10.0)

    def test_run_quit_immediately(self):
        game = make_open_game()
        source = ScriptedInput([], quit_when_done=True)
        stats = run(game, input_source=source, show=False, realtime=False)
        self.assertEqual(stats["frames"], 0.0)

    def test_make_game_random(self):
        game = make_game("random", seed=7, width=64, height=20)
        self.assertEqual(game.gmap.name, "random")
        self.assertEqual((game.width, game.height), (64, 20))
        lines = game.draw().split("\n")
        self.assertEqual(len(lines), 20)
        self.assertEqual(len(lines[0]), 64)


if __name__ == "__main__":
    unittest.main()
