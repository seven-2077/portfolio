"""得分规则：材质分、破坏率、剩余弹丸奖励、全拆奖励。"""
import unittest

from game import scoring


class TestScoring(unittest.TestCase):
    def test_points_rate_and_ammo_bonus(self):
        s = scoring.evaluate({"wood": 1, "glass": 2, "stone": 1}, 10, 2)
        self.assertEqual(s.destruction, 100 + 60 * 2 + 150)
        self.assertEqual(s.ammo_bonus, 400 * 2)
        self.assertEqual(s.clear_bonus, 0)
        self.assertEqual(s.total, 370 + 800)
        self.assertAlmostEqual(s.rate, 0.4)
        self.assertEqual(s.broken, 4)

    def test_clear_bonus_when_all_destroyed(self):
        s = scoring.evaluate({"wood": 4}, 4, 1)
        self.assertEqual(s.clear_bonus, scoring.CLEAR_BONUS)
        self.assertEqual(s.total, 400 + 400 + scoring.CLEAR_BONUS)
        self.assertAlmostEqual(s.rate, 1.0)

    def test_zero_edges(self):
        s = scoring.evaluate({}, 5, 0)
        self.assertEqual(s.total, 0)
        self.assertAlmostEqual(s.rate, 0.0)
        # 总块数为 0 不得除零
        self.assertAlmostEqual(scoring.evaluate({"glass": 0}, 0, 1).rate, 0.0)

    def test_negative_ammo_clamped(self):
        s = scoring.evaluate({"stone": 1}, 3, -2)
        self.assertEqual(s.ammo_bonus, 0)
        self.assertEqual(s.total, 150)


if __name__ == "__main__":
    unittest.main()
