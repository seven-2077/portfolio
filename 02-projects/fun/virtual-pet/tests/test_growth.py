"""成长阶段：四段年龄阈值、逐级晋升、健康停滞。"""

import unittest

from pet import growth


class TestStageTable(unittest.TestCase):
    def test_four_stages_in_order(self):
        keys = [s.key for s in growth.STAGES]
        self.assertEqual(keys, ["egg", "baby", "adult", "elder"])
        ages = [s.min_age for s in growth.STAGES]
        self.assertEqual(ages, sorted(ages))
        self.assertEqual(len(growth.STAGES), 4)

    def test_age_stage_thresholds(self):
        self.assertEqual(growth.age_stage(0), 0)
        self.assertEqual(growth.age_stage(3599), 0)
        self.assertEqual(growth.age_stage(3600), 1)
        self.assertEqual(growth.age_stage(6 * 3600), 2)
        self.assertEqual(growth.age_stage(10 * 3600), 3)
        self.assertEqual(growth.age_stage(99 * 3600), 3)

    def test_stage_danger_decreases_with_age(self):
        self.assertGreater(growth.STAGES[0].hunger_danger,
                           growth.STAGES[-1].hunger_danger)

    def test_stage_at_clamps_bounds(self):
        self.assertEqual(growth.stage_at(-5).key, "egg")
        self.assertEqual(growth.stage_at(99).key, "elder")


class TestGrowthTransitions(unittest.TestCase):
    def test_grows_one_step_when_healthy(self):
        idx, msg = growth.try_grow(0, 3601, health=90)
        self.assertEqual(idx, 1)
        self.assertIn("幼年", msg)

    def test_grows_adult_then_elder_step_by_step(self):
        idx, msg = growth.try_grow(1, 20 * 3600, health=90)
        self.assertEqual(idx, 2)                # 一次只晋一级
        self.assertIn("成年", msg)
        idx, msg = growth.try_grow(2, 20 * 3600, health=90)
        self.assertEqual(idx, 3)
        self.assertIn("老年", msg)

    def test_low_health_blocks_growth(self):
        idx, msg = growth.try_grow(1, 8 * 3600, health=49)
        self.assertEqual(idx, 1)                # 停滞
        self.assertIn("营养不足", msg)

    def test_no_growth_when_too_young(self):
        idx, msg = growth.try_grow(0, 100, health=90)
        self.assertEqual(idx, 0)
        self.assertIsNone(msg)

    def test_growth_never_regresses(self):
        idx, msg = growth.try_grow(3, 0, health=0)   # 年龄归零也不降级
        self.assertEqual(idx, 3)
        self.assertIsNone(msg)


if __name__ == "__main__":
    unittest.main()
