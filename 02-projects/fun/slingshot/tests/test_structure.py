"""结构：堆叠静止稳定性、休眠、材质碎裂阈值、连锁。"""
import math
import unittest

from game import level as lvl
from game.level import BlockDef
from game.world import World
from physics.structure import MATERIALS, Block


def stack_spec():
    return lvl.make_spec(
        [
            BlockDef(50, 27.5, 2, 1, "wood"),
            BlockDef(50, 26.5, 2, 1, "wood"),
            BlockDef(50, 25.5, 1, 1, "glass"),
        ]
    )


class TestStackStability(unittest.TestCase):
    def test_stack_rest_100_steps_near_zero_displacement(self):
        """堆叠静置 100 步位移近零（休眠防抖）。"""
        w = World(stack_spec())
        for _ in range(150):
            w.step()
        self.assertTrue(all(b.p.sleeping for b in w.blocks))
        snap = [(b.p.x, b.p.y) for b in w.blocks]
        for _ in range(100):
            w.step()
        drift = max(
            math.hypot(a[0] - b[0], a[1] - b[1])
            for a, b in zip(snap, [(b.p.x, b.p.y) for b in w.blocks])
        )
        self.assertLess(drift, 1e-9)
        self.assertEqual(w.broken, 0, "静置不得磨损结构")

    def test_dormancy_freezes_body(self):
        """休眠判定触发后坐标完全冻结。"""
        w = World(lvl.make_spec([BlockDef(50, 27.5, 2, 1, "wood")]))
        for _ in range(80):
            w.step()
        self.assertTrue(w.blocks[0].p.sleeping)
        x, y = w.blocks[0].p.x, w.blocks[0].p.y
        for _ in range(50):
            w.step()
        self.assertEqual((w.blocks[0].p.x, w.blocks[0].p.y), (x, y))


class TestMaterialThresholds(unittest.TestCase):
    def test_durability_order(self):
        self.assertLess(MATERIALS["glass"].durability, MATERIALS["wood"].durability)
        self.assertLess(MATERIALS["wood"].durability, MATERIALS["stone"].durability)
        self.assertLess(MATERIALS["glass"].density, MATERIALS["stone"].density)

    def test_impact_below_threshold_survives(self):
        self.assertFalse(Block(0, 0, 1, 1, "glass").impact(7.0))
        self.assertFalse(Block(0, 0, 1, 1, "wood").impact(20.0))
        self.assertFalse(Block(0, 0, 1, 1, "stone").impact(30.0))

    def test_impact_above_threshold_shatters(self):
        self.assertTrue(Block(0, 0, 1, 1, "glass").impact(9.0))
        self.assertTrue(Block(0, 0, 1, 1, "wood").impact(30.0))
        self.assertTrue(Block(0, 0, 1, 1, "stone").impact(40.0))

    def test_accumulated_damage_breaks(self):
        """单发不足阈值时累计耗损，总和超阈值照样碎。"""
        b = Block(0, 0, 1, 1, "wood")
        self.assertFalse(b.impact(15.0))
        self.assertTrue(b.alive)
        self.assertAlmostEqual(b.hp, 11.0)
        self.assertTrue(b.impact(12.0))
        self.assertFalse(b.alive)

    def test_tiny_contact_ignored(self):
        """低于损伤下限的微接触不掉血（静置零磨损）。"""
        b = Block(0, 0, 1, 1, "wood")
        b.impact(0.5)
        b.impact(0.5)
        self.assertAlmostEqual(b.hp, MATERIALS["wood"].durability)


class TestChainReaction(unittest.TestCase):
    def test_destroy_support_shatters_faller(self):
        """抽掉支撑 → 上方玻璃自由落体摔碎（连锁）。"""
        spec = lvl.make_spec(
            [
                BlockDef(55, 24, 1.5, 8, "wood"),
                BlockDef(55, 19.5, 3, 1, "glass"),
            ]
        )
        w = World(spec)
        for _ in range(120):
            w.step()
        self.assertTrue(all(b.p.sleeping for b in w.blocks), "初始应全部休眠")

        wood, glass = w.blocks
        w._damage(wood, 100.0)  # 模拟大冲量击碎支撑
        self.assertFalse(wood.alive)
        w.settle(4000)
        self.assertTrue(w.quiet)
        self.assertEqual(sorted(e.material for e in w.events), ["glass", "wood"])
        self.assertEqual(len(w.blocks), 0, "玻璃应被唤醒并摔碎")


if __name__ == "__main__":
    unittest.main()
