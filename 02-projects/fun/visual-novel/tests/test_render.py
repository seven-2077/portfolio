# -*- coding: utf-8 -*-
"""vn.render 测试：ANSI 配色、场景框/名牌/选项编号、打字机与跳过、历史与结局。"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vn.render import ANSI_RE, Renderer, display_width, strip_ansi
from vn.state import HistoryEntry


def make(**kw):
    buf = io.StringIO()
    defaults = dict(stream=buf, color=False, cps=0, interactive=False)
    defaults.update(kw)
    return Renderer(**defaults), buf


class TestColoring(unittest.TestCase):
    def test_color_on_emits_ansi(self):
        r, buf = make(color=True)
        r.banner("标题")
        self.assertIn("\x1b[", buf.getvalue())

    def test_color_off_is_pure_text(self):
        r, buf = make(color=False)
        r.banner("标题")
        r.notice("提示")
        r.warn("警告")
        self.assertNotIn("\x1b[", buf.getvalue())

    def test_strip_ansi_roundtrip(self):
        r, _ = make(color=True)
        colored = r._c("你好", "cyan", "bold")
        self.assertNotEqual(colored, "你好")
        self.assertEqual(strip_ansi(colored), "你好")

    def test_ansi_regex_matches_sequences(self):
        self.assertEqual(ANSI_RE.sub("", "\x1b[36m青\x1b[0m"), "青")


class TestLayout(unittest.TestCase):
    def test_scene_box_contains_title(self):
        r, buf = make()
        r.scene("放学后的教室")
        out = buf.getvalue()
        self.assertIn("放学后的教室", out)
        self.assertIn("╭", out)
        self.assertIn("╰", out)

    def test_scene_box_lines_aligned(self):
        # 顶/底横线与标题行在东亚全角宽度下应等宽
        r, buf = make()
        r.scene("天台")
        lines = [l for l in buf.getvalue().splitlines() if l]
        widths = [display_width(l) for l in lines[:3]]
        self.assertEqual(len(set(widths)), 1, f"框线未对齐: {widths}")

    def test_line_has_speaker名牌(self):
        r, buf = make()
        r.line("澪", "……你也来啦。")
        out = buf.getvalue()
        self.assertIn("【澪】", out)
        self.assertIn("……你也来啦。", out)

    def test_choices_numbered(self):
        r, buf = make()
        r.choices(["拉她走", "留下", "离开"])
        out = buf.getvalue()
        self.assertIn("1. 拉她走", strip_ansi(out))
        self.assertIn("2. 留下", strip_ansi(out))
        self.assertIn("3. 离开", strip_ansi(out))

    def test_ending_banner_contains_name(self):
        r, buf = make()
        r.ending("一起去看海")
        self.assertIn("一起去看海", buf.getvalue())
        self.assertIn("结局", buf.getvalue())

    def test_ending_banner_lines_aligned(self):
        r, buf = make()
        r.ending("一起去看海")
        lines = [l for l in buf.getvalue().splitlines() if l]
        widths = [display_width(l) for l in lines[:3]]
        self.assertEqual(len(set(widths)), 1, f"横幅未对齐: {widths}")

    def test_fx_marker_rendered(self):
        r, buf = make()
        r.fx("sfx", "radio_static")
        self.assertIn("radio_static", buf.getvalue())
        self.assertIn("sfx", buf.getvalue())

    def test_chosen_echo(self):
        r, buf = make()
        r.chosen("拉她走")
        self.assertIn("拉她走", buf.getvalue())

    def test_banner_and_subtitle(self):
        r, buf = make()
        r.banner("rain_signal", "剧本来源：rain_signal.vn")
        out = buf.getvalue()
        self.assertIn("rain_signal", out)
        self.assertIn("剧本来源", out)


class TestTypewriter(unittest.TestCase):
    def test_instant_mode_writes_full_text(self):
        r, buf = make(cps=0, interactive=True)
        r.typewriter("一段完整的台词")
        self.assertEqual(buf.getvalue().strip(), "一段完整的台词")

    def test_cps_sleeps_per_char_and_keeps_text(self):
        sleeps = []
        r, buf = make(cps=10, interactive=True, sleeper=sleeps.append)
        r.line("澪", "你好世界")
        out = buf.getvalue()
        self.assertIn("你好世界", out)
        # 非换行字符逐个 sleep（"你好世界" 4 字）
        self.assertEqual(len(sleeps), 4)
        self.assertAlmostEqual(sleeps[0], 0.1)

    def test_key_poll_skips_ahead_but_text_complete(self):
        sleeps = []
        r, buf = make(cps=10, interactive=True, sleeper=sleeps.append)
        r.key_poll = lambda: " "  # 任意键：立即跳过
        r.narration("这行字很多，本来要逐字慢慢打出来")
        out = strip_ansi(buf.getvalue())
        self.assertIn("这行字很多，本来要逐字慢慢打出来", out)
        self.assertLess(len(sleeps), len("这行字很多，本来要逐字慢慢打出来"))

    def test_non_interactive_never_sleeps(self):
        sleeps = []
        r, buf = make(cps=10, interactive=False, sleeper=sleeps.append)
        r.line("澪", "不该有节奏")
        self.assertEqual(sleeps, [])
        self.assertIn("不该有节奏", buf.getvalue())


class TestHistoryView(unittest.TestCase):
    def test_renders_all_kinds(self):
        r, buf = make()
        entries = [
            HistoryEntry("scene", scene="天台"),
            HistoryEntry("line", speaker="澪", text="你也来啦", scene="天台"),
            HistoryEntry("narration", text="雨停了"),
            HistoryEntry("choice", choice={"index": 1, "text": "拉她走"}),
            HistoryEntry("fx", text="sfx:radio"),
            HistoryEntry("ending", text="一起去看海"),
        ]
        r.history_view(entries)
        out = strip_ansi(buf.getvalue())
        for frag in ("天台", "澪", "你也来啦", "雨停了", "拉她走", "sfx:radio", "一起去看海"):
            self.assertIn(frag, out)

    def test_empty_history(self):
        r, buf = make()
        r.history_view([])
        self.assertIn("暂无", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
