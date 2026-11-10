"""Gray-Scott 反应扩散测试：确定性、数值边界、预设统计可分性。"""

import unittest

from lifelab.grey_scott import PRESETS, GrayScott


class TestDeterminism(unittest.TestCase):
    def test_single_step_deterministic(self):
        a = GrayScott(32, 32, feed=0.037, kill=0.06)
        b = GrayScott(32, 32, feed=0.037, kill=0.06)
        a.step()
        b.step()
        self.assertEqual(a.field_u(), b.field_u())
        self.assertEqual(a.field_v(), b.field_v())

    def test_many_steps_deterministic(self):
        a = GrayScott(24, 24, feed=0.055, kill=0.062)
        b = GrayScott(24, 24, feed=0.055, kill=0.062)
        a.run(60)
        b.run(60)
        self.assertEqual(a.field_v(), b.field_v())
        self.assertEqual(a.generation, 60)

    def test_seed_is_localized_and_deterministic(self):
        sim = GrayScott(48, 48)
        u, v = sim.field_u(), sim.field_v()
        center = 24 * 48 + 24
        self.assertEqual(v[0], 0.0)  # 角落未播种
        self.assertEqual(u[0], 1.0)
        self.assertAlmostEqual(v[center], 0.25)  # 中心方块 U=0.50, V=0.25
        self.assertAlmostEqual(u[center], 0.50)


class TestStability(unittest.TestCase):
    def test_bounds_after_many_steps(self):
        for lap in ("5", "9"):
            with self.subTest(lap=lap):
                sim = GrayScott(40, 40, feed=0.055, kill=0.062, lap=lap)
                sim.run(200)
                for val in sim.field_u() + sim.field_v():
                    self.assertGreaterEqual(val, 0.0)
                    self.assertLessEqual(val, 1.0)

    def test_clipping_under_extreme_params(self):
        # 极端 feed/kill/扩散系数：不抛异常，浓度仍被裁进 [0, 1]
        sim = GrayScott(24, 24, feed=0.2, kill=0.5, du=1.0, dv=1.0, lap="9")
        sim.run(50)
        for val in sim.field_u() + sim.field_v():
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)

    def test_invalid_args_raise(self):
        with self.assertRaises(ValueError):
            GrayScott(10, 10, lap="7")
        with self.assertRaises(ValueError):
            GrayScott(0, 10)
        with self.assertRaises(ValueError):
            GrayScott(10, 10, feed=2.0)
        with self.assertRaises(ValueError):
            GrayScott(10, 10, dv=-0.1)
        with self.assertRaises(ValueError):
            GrayScott(10, 10).run(-1)

    def test_laplacian_modes_differ_but_agree_stably(self):
        a = GrayScott(32, 32, lap="5", feed=0.04, kill=0.06)
        b = GrayScott(32, 32, lap="9", feed=0.04, kill=0.06)
        a.run(80)
        b.run(80)
        self.assertNotEqual(a.field_v(), b.field_v())  # 模板不同 → 数值不同
        for sim in (a, b):
            for val in sim.field_v():
                self.assertTrue(0.0 <= val <= 1.0)


class TestPresets(unittest.TestCase):
    def test_presets_registered(self):
        self.assertEqual(set(PRESETS), {"spots", "stripes", "worms"})
        for p in PRESETS.values():
            with self.subTest(preset=p.name):
                self.assertTrue(p.label and p.note)
                self.assertGreater(p.feed, 0.0)
                self.assertGreater(p.kill, 0.0)

    def test_from_preset_matches_registry(self):
        sim = GrayScott.from_preset(20, 20, "spots")
        self.assertAlmostEqual(sim.feed, PRESETS["spots"].feed)
        self.assertAlmostEqual(sim.kill, PRESETS["spots"].kill)
        with self.assertRaises(KeyError):
            GrayScott.from_preset(20, 20, "nope")

    def test_presets_grow_and_stay_alive(self):
        """三组预设都要真的长出结构（demo 图集不能是空场）。"""
        for name in PRESETS:
            with self.subTest(preset=name):
                sim = GrayScott.from_preset(48, 48, name)
                sim.run(400)
                st = sim.stats()
                self.assertGreater(st["mean_v"], 0.005, "V 场应从种子长起来")
                self.assertGreater(st["occupied"], 0.01, "结构应占据一定面积")

    def test_presets_produce_distinguishable_statistics(self):
        """feed/kill 不同 → 统计特征（边缘密度/占据率）可区分。"""
        stats = {}
        for name in PRESETS:
            sim = GrayScott.from_preset(48, 48, name)
            sim.run(400)
            stats[name] = sim.stats()
        edges = {k: v["edge_density"] for k, v in stats.items()}
        occ = {k: v["occupied"] for k, v in stats.items()}
        # 任意两组的边缘密度差要超过噪声量级
        names = list(PRESETS)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                self.assertGreater(
                    abs(edges[a] - edges[b]),
                    0.002,
                    f"{a} vs {b} 边缘密度应可区分：{edges}",
                )
        # 斑点型（稀疏孤立点）与条纹型（高补给高密度）占据率明显分开
        self.assertGreater(abs(occ["spots"] - occ["stripes"]), 0.02, occ)

    def test_stats_ranges(self):
        sim = GrayScott(32, 32)
        sim.run(100)
        st = sim.stats()
        self.assertGreaterEqual(st["edge_density"], 0.0)
        self.assertTrue(0.0 <= st["mean_u"] <= 1.0)
        self.assertTrue(0.0 <= st["mean_v"] <= 1.0)
        self.assertTrue(0.0 <= st["occupied"] <= 1.0)
        self.assertEqual(st["generation"], 100.0)

    def test_run_returns_self(self):
        sim = GrayScott(16, 16)
        self.assertIs(sim.run(7), sim)
        self.assertEqual(sim.generation, 7)


if __name__ == "__main__":
    unittest.main()
