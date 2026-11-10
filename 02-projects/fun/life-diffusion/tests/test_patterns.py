"""图案库测试：元信息完整性、经典图案几何、枪炮实际出弹。"""

import dataclasses
import unittest

from lifelab.patterns import PATTERNS, Pattern, get_pattern

REQUIRED = ("glider", "blinker", "pulsar", "gosper_glider_gun")


class TestRegistry(unittest.TestCase):
    def test_required_patterns_present(self):
        for name in REQUIRED:
            self.assertIn(name, PATTERNS)

    def test_metadata_complete(self):
        for p in PATTERNS.values():
            with self.subTest(pattern=p.name):
                self.assertTrue(p.name)
                self.assertIn(p.category, ("spaceship", "oscillator", "gun"))
                self.assertGreaterEqual(p.period, 1)
                self.assertTrue(p.discovered_by)
                self.assertGreaterEqual(p.year, 1969)
                self.assertTrue(p.description)
                self.assertGreaterEqual(p.width * p.height, 1)

    def test_glider_metadata(self):
        g = get_pattern("glider")
        self.assertEqual(g.period, 4)
        self.assertTrue(g.translates)
        self.assertEqual(g.translation, (1, 1))
        self.assertEqual(g.category, "spaceship")

    def test_pattern_is_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            get_pattern("blinker").period = 99  # type: ignore[misc]

    def test_alias_lookup(self):
        self.assertIs(get_pattern("Gosper Glider Gun"), PATTERNS["gosper_glider_gun"])
        self.assertIs(get_pattern("gun"), PATTERNS["gosper_glider_gun"])
        self.assertIs(get_pattern("滑翔机"), PATTERNS["glider"])
        self.assertEqual(get_pattern(" blinker ").name, "blinker")

    def test_unknown_pattern_raises(self):
        with self.assertRaises(KeyError):
            get_pattern("definitely-not-a-pattern")


class TestGeometry(unittest.TestCase):
    def test_glider_geometry(self):
        g = get_pattern("glider")
        self.assertEqual((g.width, g.height), (3, 3))
        self.assertEqual(len(g.cells), 5)

    def test_blinker_geometry(self):
        b = get_pattern("blinker")
        self.assertEqual((b.width, b.height), (3, 1))
        self.assertEqual(len(b.cells), 3)

    def test_pulsar_geometry(self):
        p = get_pattern("pulsar")
        self.assertEqual((p.width, p.height), (13, 13))
        self.assertEqual(len(p.cells), 48)

    def test_gosper_gun_geometry(self):
        gun = get_pattern("gosper_glider_gun")
        self.assertEqual((gun.width, gun.height), (36, 9))
        self.assertEqual(len(gun.cells), 36)
        self.assertEqual(gun.period, 30)
        self.assertEqual(gun.discovered_by, "Bill Gosper")
        self.assertEqual(gun.year, 1970)

    def test_cells_at_applies_origin(self):
        shifted = get_pattern("glider").cells_at((5, 5))
        self.assertEqual(min(x for x, _ in shifted), 5)
        self.assertEqual(min(y for _, y in shifted), 5)

    def test_to_game_default_and_custom_size(self):
        g = get_pattern("glider").to_game(origin=(2, 3))
        self.assertEqual((g.width, g.height), (5, 6))
        self.assertEqual(g.population, 5)
        big = get_pattern("blinker").to_game(20, 10)
        self.assertEqual((big.width, big.height), (20, 10))


class TestPatternDynamics(unittest.TestCase):
    def test_blinker_period_two(self):
        b = get_pattern("blinker").to_game(7, 7, origin=(2, 3))
        before = b.live_cells
        b.step()
        self.assertNotEqual(b.live_cells, before)
        b.step()
        self.assertEqual(b.live_cells, before)

    def test_pulsar_period_three(self):
        # 中间相（56/72 格）会向外扩一格，故须留边距再测周期
        p = get_pattern("pulsar").to_game(17, 17, origin=(2, 2))
        before = p.live_cells
        p.step()
        self.assertNotEqual(p.live_cells, before)  # 中间态确实不同
        self.assertEqual(p.population, 56)  # CP 48-56-72 相位序列
        p.step()
        self.assertEqual(p.population, 72)
        p.step()
        self.assertEqual(p.live_cells, before)

    def test_glider_translates_after_four(self):
        glider = get_pattern("glider")
        game = glider.to_game(16, 16, origin=(2, 2))
        game.run(4)
        expected = {(x + 3, y + 3) for x, y in glider.cells}
        self.assertEqual(game.live_cells, frozenset(expected))


class TestGosperGun(unittest.TestCase):
    def test_gun_emits_gliders_far_field(self):
        """240 步后应有至少两架滑翔机飞出枪体（无界增长的直接证据）。"""
        gun = get_pattern("gosper_glider_gun")
        game = gun.to_game(220, 160)
        self.assertEqual(game.population, 36)
        game.run(240)
        far = [c for c in game.live_cells if c[0] >= 45]
        self.assertGreaterEqual(
            len(far), 10, "枪应在 240 步内把至少两架滑翔机送出 x>=45 的远场"
        )
        # 包围盒持续扩张 = 确实长出了无界结构
        box = game.bbox()
        self.assertIsNotNone(box)
        self.assertGreater(box[2], 60)

    def test_gun_start_population_oscillates_but_never_dies(self):
        game = get_pattern("gosper_glider_gun").to_game(120, 60)
        for gen in range(1, 121):
            game.step()
            self.assertGreaterEqual(game.population, 30, f"gen {gen} 枪体不应衰减")


if __name__ == "__main__":
    unittest.main()
