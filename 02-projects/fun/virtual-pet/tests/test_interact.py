"""终端交互：固定步数演示模式（非 TTY）、按键轮询、动作映射。"""

import unittest

from pet import engine, interact


class TestScriptMode(unittest.TestCase):
    def test_fixed_steps_demo_mode_runs(self):
        lines = []
        clock = {"t": 1_000_000.0}

        def now_fn():
            clock["t"] += 60
            return clock["t"]

        pet = engine.new_pet(now=1_000_000.0)
        log = interact.run(pet, steps=3, script=("feed", "status"),
                           now_fn=now_fn, out=lines.append)
        joined = "\n".join(lines)
        self.assertIn("virtual-pet", joined)       # 首屏渲染
        self.assertIn("喂食", joined)               # 动作日志
        self.assertIn("详情", joined)               # status → 详情页
        self.assertIn("饱食", joined)               # 状态条
        self.assertGreaterEqual(len(log), 3)

    def test_script_step_includes_advance_events(self):
        lines = []
        clock = {"t": 1_000_000.0}

        def now_fn():
            clock["t"] += 7200                    # 每步跳 2 小时（离线）
            return clock["t"]

        pet = engine.new_pet(now=1_000_000.0)
        interact.run(pet, steps=2, script=("status",),
                     now_fn=now_fn, out=lines.append)
        self.assertGreater(pet.age_seconds, 0)     # 时间确实推进了
        self.assertGreater(pet.hunger, 30)         # 而且变饿了


class TestKeys(unittest.TestCase):
    def test_read_key_timeout_returns_none(self):
        self.assertIsNone(interact.read_key(timeout=0,
                                            sleep_fn=lambda s: None))

    def test_action_name_mapping(self):
        self.assertEqual(interact.action_name("1"), "喂食")
        self.assertEqual(interact.action_name("2"), "玩耍")
        self.assertEqual(interact.action_name("3"), "睡觉")
        self.assertEqual(interact.action_name("wake"), "醒来")
        self.assertEqual(interact.action_name("status"), "状态")


if __name__ == "__main__":
    unittest.main()
