"""状态机转移与真实时间演化的测试（时间戳全部注入，完全可复现）。"""

import unittest

from pet import engine

T0 = 1_000_000.0


def make_pet(**overrides):
    pet = engine.new_pet(now=T0)
    for key, value in overrides.items():
        setattr(pet, key, value)
    return pet


class TestActions(unittest.TestCase):
    """玩家动作 → 状态机输入。"""

    def test_new_pet_defaults(self):
        pet = engine.new_pet(now=T0)
        self.assertEqual(pet.last_tick, T0)
        self.assertEqual(pet.status, engine.IDLE)
        self.assertEqual(pet.hunger, 30)
        self.assertEqual(pet.stage_idx, 0)

    def test_feed_raises_fullness_and_enters_eating(self):
        pet = make_pet(hunger=60)
        result = engine.feed(pet)
        self.assertTrue(result.ok)
        self.assertLess(pet.hunger, 60)
        self.assertEqual(pet.status, engine.EATING)
        self.assertGreater(pet.action_left, 0)

    def test_feed_applies_study_bonus(self):
        pet = make_pet(hunger=80, mood=70)
        result = engine.feed(pet, bonus=0.5)     # 35 * 1.5 = 52.5
        self.assertAlmostEqual(pet.hunger, 27.5)
        self.assertAlmostEqual(pet.mood, 77.5)
        self.assertIn("+50%", result.message)

    def test_feed_rejected_while_sleeping(self):
        pet = make_pet()
        engine.sleep(pet)
        result = engine.feed(pet)
        self.assertFalse(result.ok)
        self.assertEqual(pet.status, engine.SLEEPING)

    def test_play_raises_mood_and_spends_energy(self):
        pet = make_pet(mood=50, energy=80, hunger=30)
        result = engine.play(pet)
        self.assertTrue(result.ok)
        self.assertGreater(pet.mood, 50)
        self.assertLess(pet.energy, 80)
        self.assertEqual(pet.status, engine.PLAYING)

    def test_play_rejected_when_exhausted(self):
        pet = make_pet(energy=10)
        result = engine.play(pet)
        self.assertFalse(result.ok)
        self.assertIn("太累", result.message)
        self.assertEqual(pet.status, engine.IDLE)

    def test_play_rejected_when_sick(self):
        pet = make_pet(status=engine.SICK, health=20)
        result = engine.play(pet)
        self.assertFalse(result.ok)
        self.assertIn("病", result.message)

    def test_sleep_wake_roundtrip(self):
        pet = make_pet()
        self.assertTrue(engine.sleep(pet).ok)
        self.assertEqual(pet.status, engine.SLEEPING)
        self.assertFalse(engine.sleep(pet).ok)      # 已经睡了
        self.assertTrue(engine.wake(pet).ok)
        self.assertEqual(pet.status, engine.IDLE)
        self.assertFalse(engine.wake(pet).ok)       # 已经醒着

    def test_sleep_rejected_while_eating(self):
        pet = make_pet()
        engine.feed(pet)
        result = engine.sleep(pet)
        self.assertFalse(result.ok)
        self.assertEqual(pet.status, engine.EATING)


class TestTimeEvolution(unittest.TestCase):
    """advance() 的真实时间增量结算（注入时间戳）。"""

    def test_advance_grows_hunger_and_decays_mood(self):
        pet = make_pet(hunger=30, mood=70)
        engine.advance(pet, T0 + 3600)          # raw 1h → 离线折扣 eff 0.5h
        self.assertGreater(pet.hunger, 30)
        self.assertLess(pet.mood, 70)
        for attr in ("hunger", "mood", "energy", "health"):
            value = getattr(pet, attr)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_offline_discount_halts_long_gap(self):
        pet = make_pet()
        engine.advance(pet, T0 + 3600)          # > 离线宽限 120s → 打对折
        self.assertAlmostEqual(pet.age_seconds, 1800, delta=0.01)

    def test_offline_cap_limits_age_growth(self):
        pet = make_pet()
        engine.advance(pet, T0 + 7 * 86400)     # 离线 7 天
        self.assertLessEqual(pet.age_seconds, engine.MAX_OFFLINE_SECONDS)
        self.assertAlmostEqual(pet.age_seconds, 21600, delta=0.01)
        engine.advance(pet, T0 + 7 * 86400 + 30 * 86400)   # 再离线 30 天
        self.assertAlmostEqual(pet.age_seconds, 43200, delta=0.01)

    def test_clock_rollback_is_ignored(self):
        pet = make_pet()
        engine.advance(pet, T0 - 500)           # 时钟回拨
        self.assertEqual(pet.age_seconds, 0)
        self.assertEqual(pet.last_tick, T0 - 500)

    def test_long_starvation_hurts_health_and_makes_sick(self):
        pet = make_pet(hunger=100, health=90)
        events = engine.advance(pet, T0 + 6 * 3600)     # 饿 6 小时
        self.assertLess(pet.health, 90)
        self.assertEqual(pet.status, engine.SICK)
        self.assertTrue(any("生病" in e for e in events))

    def test_sick_announced_once_only(self):
        pet = make_pet(hunger=100, health=90)
        engine.advance(pet, T0 + 6 * 3600)              # 首次播报
        events = engine.advance(pet, T0 + 7 * 3600)     # 继续恶化
        self.assertFalse(any("生病" in e for e in events))
        self.assertEqual(pet.status, engine.SICK)

    def test_recovery_announced(self):
        pet = make_pet(status=engine.SICK, sick_noted=True,
                       health=46, stress_seconds=0)
        events = engine.advance(pet, T0 + 2)
        self.assertEqual(pet.status, engine.IDLE)
        self.assertTrue(any("康复" in e for e in events))
        self.assertFalse(pet.sick_noted)

    def test_stress_is_capped(self):
        pet = make_pet(hunger=100, energy=0)
        engine.advance(pet, T0 + 30 * 86400)
        self.assertLessEqual(pet.stress_seconds,
                             2 * engine.STRESS_SECONDS + 0.01)
        self.assertAlmostEqual(pet.stress_seconds,
                               2 * engine.STRESS_SECONDS, delta=0.01)


class TestStateTimers(unittest.TestCase):
    """短状态计时与睡眠恢复。"""

    def test_eating_finishes_back_to_idle(self):
        pet = make_pet()
        engine.feed(pet)
        engine.advance(pet, T0 + 5)                 # 未吃完
        self.assertEqual(pet.status, engine.EATING)
        events = engine.advance(pet, T0 + 11)        # 吃完
        self.assertEqual(pet.status, engine.IDLE)
        self.assertTrue(any("吃完" in e for e in events))

    def test_eating_while_sick_returns_to_sick_silently(self):
        pet = make_pet(health=20)
        events = engine.advance(pet, T0 + 1)         # 触发首次生病播报
        self.assertTrue(any("生病" in e for e in events))
        engine.feed(pet)
        events = engine.advance(pet, T0 + 20)        # 吃完 → 直接回 sick
        self.assertEqual(pet.status, engine.SICK)
        self.assertFalse(any("生病" in e for e in events))

    def test_sleep_recovers_energy(self):
        pet = make_pet(energy=10)
        engine.sleep(pet)
        engine.advance(pet, T0 + 5 * 3600)
        self.assertGreater(pet.energy, 10)
        self.assertEqual(pet.status, engine.SLEEPING)

    def test_sleep_auto_wakes_when_energy_full(self):
        pet = make_pet(energy=90)
        engine.sleep(pet)
        events = engine.advance(pet, T0 + 3 * 3600)
        self.assertEqual(pet.status, engine.IDLE)
        self.assertGreaterEqual(pet.energy, 100)
        self.assertTrue(any("醒来" in e for e in events))


if __name__ == "__main__":
    unittest.main()
