"""界面渲染（状态条/时间/加成行）与 ASCII 形象（多帧/心情）。"""

import re
import unittest

from pet import engine, growth, interact, sprites
from pet.studylink import StudyReport


class TestStatusBar(unittest.TestCase):
    def test_bar_shape_and_bounds(self):
        bar = interact.bar(50)
        self.assertEqual(len(bar), interact.BAR_WIDTH)
        self.assertEqual(bar.count("█"), 9)
        self.assertEqual(bar.count("░"), 9)
        self.assertEqual(interact.bar(0), "░" * interact.BAR_WIDTH)
        self.assertEqual(interact.bar(100), "█" * interact.BAR_WIDTH)
        self.assertEqual(interact.bar(-20), "░" * interact.BAR_WIDTH)
        self.assertEqual(interact.bar(250), "█" * interact.BAR_WIDTH)

    def test_fmt_duration(self):
        self.assertEqual(interact.fmt_duration(45), "45s")
        self.assertEqual(interact.fmt_duration(3671), "1h01m")
        self.assertEqual(interact.fmt_duration(90000), "1d1h")


class TestRender(unittest.TestCase):
    def setUp(self):
        self.pet = engine.new_pet(now=1_000_000.0)
        self.pet.stage_idx = 1                     # 幼年
        self.report = StudyReport(minutes=300, source="demo",
                                  bonus=0.5, log_path="")

    def test_render_contains_bars_and_labels(self):
        out = interact.render(self.pet, self.report, now=1_000_000.0)
        for label in ("饱食", "心情", "能量", "健康"):
            self.assertIn(label, out)
        self.assertIn("█", out)
        self.assertIn("░", out)
        self.assertGreaterEqual(out.count("█"), 4)

    def test_render_contains_clock_and_stage(self):
        out = interact.render(self.pet, self.report, now=1_000_000.0)
        self.assertRegex(out, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertIn("[幼年]", out)
        self.assertIn("小煤球", out)

    def test_render_shows_study_bonus_line(self):
        out = interact.render(self.pet, self.report, now=1_000_000.0)
        self.assertIn("喂食加成 +50%", out)
        self.assertIn("演示数据", out)
        real = StudyReport(minutes=210, source="study-timer",
                           bonus=0.4375, log_path="/x/log.json")
        out2 = interact.render(self.pet, real, now=1_000_000.0)
        self.assertIn("study-timer", out2)

    def test_render_menu_and_status_zh(self):
        out = interact.render(self.pet, self.report, now=1_000_000.0)
        self.assertIn("[1]喂食", out)
        self.assertIn("状态：空闲", out)
        self.pet.status = engine.SLEEPING
        out = interact.render(self.pet, self.report, now=1_000_000.0)
        self.assertIn("睡觉中", out)

    def test_detail_page_shows_thresholds(self):
        out = interact.detail(self.pet, self.report)
        self.assertIn("压力累计", out)
        self.assertIn("饥饿警戒线", out)
        self.assertIn("幼年", out)


class TestSprites(unittest.TestCase):
    def test_frames_alternate_blinking(self):
        for stage in ("egg", "baby", "adult", "elder"):
            open_frame = sprites.get_sprite(stage, 80, frame=0)
            shut_frame = sprites.get_sprite(stage, 80, frame=1)
            self.assertNotEqual(open_frame, shut_frame, stage)

    def test_mood_changes_face(self):
        happy = sprites.get_sprite("adult", 90, frame=0)
        miserable = sprites.get_sprite("adult", 5, frame=0)
        self.assertNotEqual(happy, miserable)

    def test_sleeping_shows_zzz(self):
        out = sprites.get_sprite("adult", 80, frame=0, sleeping=True)
        self.assertIn("z Z z", out)
        self.assertEqual(out.count("-   -"), 1)      # 强制闭眼

    def test_all_stages_render_clean(self):
        for stage in ("egg", "baby", "adult", "elder"):
            out = sprites.get_sprite(stage, 50, frame=0)
            self.assertTrue(out.strip(), stage)
            self.assertNotIn("{", out, stage)         # 占位符全部填充
            self.assertNotIn("}", out, stage)

    def test_mood_key_buckets(self):
        self.assertEqual(sprites.mood_key(75), "happy")
        self.assertEqual(sprites.mood_key(74), "normal")
        self.assertEqual(sprites.mood_key(50), "normal")
        self.assertEqual(sprites.mood_key(49), "sad")
        self.assertEqual(sprites.mood_key(25), "sad")
        self.assertEqual(sprites.mood_key(24), "miserable")


if __name__ == "__main__":
    unittest.main()
