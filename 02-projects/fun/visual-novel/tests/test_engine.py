# -*- coding: utf-8 -*-
"""vn.engine 测试：跳转/条件跳转、好感度阈值结局、自动选项、历史、存读档、退出。"""

import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vn.engine import DEFAULT_ENDING, Engine, EngineConfig, EngineError
from vn.render import Renderer
from vn.script import parse_script
from vn.state import State

STORY_DIR = Path(__file__).resolve().parent.parent / "story"
SAVE_SCRIPT = STORY_DIR / "rain_signal.vn"


def make_engine(src, *, autoplay=True, input_seq=(), save_dir=None,
                 state=None, story_name="test.vn"):
    """构造引擎：StringIO 捕获输出，input_seq 驱动交互输入。"""
    buf = io.StringIO()
    script = parse_script(src, story_name)
    renderer = Renderer(stream=buf, color=False, cps=0)
    config = EngineConfig(autoplay=autoplay, banner=False,
                          save_dir=str(save_dir or "."))
    it = iter(list(input_seq))

    def input_fn(_prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    engine = Engine(script, renderer=renderer, config=config,
                    input_fn=input_fn, state=state)
    return engine, buf


class TestFlow(unittest.TestCase):
    def test_jump_skips_block(self):
        engine, buf = make_engine(
            "@label start\n|before\n@jump past\n|skipped\n"
            "@label past\n|after\n@end\n")
        ending = engine.run()
        text = buf.getvalue()
        self.assertIn("before", text)
        self.assertIn("after", text)
        self.assertNotIn("skipped", text)
        self.assertEqual(ending, DEFAULT_ENDING)

    def test_conditional_jump_taken_when_true(self):
        src = "@if flag == 1 -> hit\n|missed\n@end\n@label hit\n|hit_reached\n@end\n"
        engine, buf = make_engine(src, state=State(variables={"flag": 1}))
        engine.run()
        self.assertIn("hit_reached", buf.getvalue())
        self.assertNotIn("missed", buf.getvalue())

    def test_conditional_jump_falls_through_when_false(self):
        src = "@if flag == 1 -> hit\n|missed\n@end\n@label hit\n|hit_reached\n@end\n"
        engine, buf = make_engine(src, state=State(variables={"flag": 0}))
        engine.run()
        self.assertIn("missed", buf.getvalue())
        self.assertNotIn("hit_reached", buf.getvalue())

    def test_set_accumulates_before_branch(self):
        src = "@set affection += 2\n@set affection += 3\n@end 大结局\n"
        engine, _ = make_engine(src)
        self.assertEqual(engine.run(), "大结局")
        self.assertEqual(engine.state.affection, 5)

    def test_explicit_end_name_wins(self):
        engine, _ = make_engine(
            "@ending 阈值结局 when affection >= 99\n|hi\n@end 直接结局\n")
        self.assertEqual(engine.run(), "直接结局")


class TestAffectionEndings(unittest.TestCase):
    """好感度阈值触发不同结局（多结局判定核心）。"""

    SRC = (
        "@ending 大满 when affection >= 5\n"
        "@ending 小胜 when affection >= 2\n"
        "|start\n"
        "@set affection += {add}\n"
        "@end\n")

    def run_with(self, add):
        engine, buf = make_engine(self.SRC.format(add=add))
        ending = engine.run()
        return ending, engine

    def test_high_affection_reaches_true_end(self):
        ending, engine = self.run_with(6)
        self.assertEqual(ending, "大满")
        self.assertEqual(engine.state.affection, 6)

    def test_mid_affection_reaches_secondary_end(self):
        ending, _ = self.run_with(3)
        self.assertEqual(ending, "小胜")

    def test_zero_affection_falls_to_default(self):
        ending, _ = self.run_with(0)
        self.assertEqual(ending, DEFAULT_ENDING)

    def test_rules_evaluated_in_declaration_order(self):
        # affection=7 同时满足两条，取先声明的
        ending, _ = self.run_with(7)
        self.assertEqual(ending, "大满")


class TestChoices(unittest.TestCase):
    BRANCHES = (
        "@choice\n- 第一项 -> a1\n- 第二项 -> a2\n"
        "@label a1\n|picked_first\n@end 路线A\n"
        "@label a2\n|picked_second\n@end 路线B\n")

    def test_autoplay_picks_first_option(self):
        engine, buf = make_engine(self.BRANCHES, autoplay=True)
        self.assertEqual(engine.run(), "路线A")
        self.assertIn("picked_first", buf.getvalue())
        # 历史里应留下所选选项
        choices = [h for h in engine.state.history if h.kind == "choice"]
        self.assertEqual(choices[0].choice["text"], "第一项")

    def test_interactive_selects_second_option(self):
        engine, buf = make_engine(self.BRANCHES, autoplay=False,
                                  input_seq=["2", "", ""])
        self.assertEqual(engine.run(), "路线B")
        self.assertIn("picked_second", buf.getvalue())

    def test_interactive_retries_on_bad_input(self):
        engine, buf = make_engine(self.BRANCHES, autoplay=False,
                                  input_seq=["9", "abc", "2", "", ""])
        self.assertEqual(engine.run(), "路线B")
        self.assertIn("编号超出范围", buf.getvalue())
        self.assertIn("请输入选项编号", buf.getvalue())

    def test_empty_input_defaults_to_first(self):
        engine, _ = make_engine(self.BRANCHES, autoplay=False,
                                input_seq=["", ""])
        self.assertEqual(engine.run(), "路线A")

    def test_conditional_option_hidden_when_false(self):
        src = (
            "@choice\n- [secret == 1] 暗门 -> hidden\n- 明路 -> open\n"
            "@label hidden\n|behind_secret\n@end 暗线\n"
            "@label open\n|normal_path\n@end 明线\n")
        engine, buf = make_engine(src, state=State(variables={"secret": 0}))
        self.assertEqual(engine.run(), "明线")
        self.assertNotIn("暗门", buf.getvalue())

    def test_conditional_option_visible_when_true(self):
        src = (
            "@choice\n- [secret == 1] 暗门 -> hidden\n- 明路 -> open\n"
            "@label hidden\n|behind_secret\n@end 暗线\n"
            "@label open\n|normal_path\n@end 明线\n")
        engine, buf = make_engine(src, state=State(variables={"secret": 1}))
        self.assertEqual(engine.run(), "暗线")
        self.assertIn("暗门", buf.getvalue())

    def test_all_options_hidden_raises(self):
        src = (
            "@choice\n- [a == 1] 甲 -> x\n- [b == 1] 乙 -> y\n"
            "@label x\n@end\n@label y\n@end\n")
        engine, _ = make_engine(src, state=State())
        with self.assertRaises(EngineError):
            engine.run()

    def test_unknown_jump_label_rejected_at_parse(self):
        # 解析期的后置校验就会拦下（引擎运行期不再遇到这种剧本）
        from vn.script import ScriptError
        with self.assertRaises(ScriptError):
            make_engine("|hi\n@jump gone\n@end\n")


class TestCommands(unittest.TestCase):
    TWO_LINES = "|one\n|two\n@end 结束\n"

    def test_save_command_writes_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine, buf = make_engine(self.TWO_LINES, autoplay=False,
                                      input_seq=["s 1", "", ""],
                                      save_dir=tmp)
            self.assertEqual(engine.run(), "结束")
            self.assertTrue((Path(tmp) / "slot_1.json").is_file())
            self.assertIn("已存档", buf.getvalue())

    def test_load_resumes_mid_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 先造一个存档：跳过第一行，变量好感度 3
            saved = State(script_name="test", line_index=1)
            saved.set("affection", 3)
            saved.save_to(2, tmp)
            loaded = State.load_from(2, tmp, expect_script="test")

            src = ("|one\n|two\n"
                   "@ending 高好感 when affection >= 3\n"
                   "@end\n")
            engine, buf = make_engine(src, state=loaded, autoplay=False,
                                      input_seq=[""])
            self.assertEqual(engine.run(), "高好感")
            self.assertNotIn("one", buf.getvalue())  # 第一行没有重放
            self.assertIn("two", buf.getvalue())

    def test_load_empty_slot_warns_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine, buf = make_engine(self.TWO_LINES, autoplay=False,
                                      input_seq=["l 7", "", ""])
            self.assertEqual(engine.run(), "结束")
            self.assertIn("为空", buf.getvalue())

    def test_quit_returns_none(self):
        engine, buf = make_engine(self.TWO_LINES, autoplay=False,
                                  input_seq=["q"])
        self.assertIsNone(engine.run())
        self.assertIn("已退出", buf.getvalue())

    def test_speed_command_changes_cps(self):
        engine, buf = make_engine(self.TWO_LINES, autoplay=False,
                                  input_seq=["+", "", ""])
        engine.run()
        self.assertGreater(engine.renderer.cps, 0)

    def test_unknown_command_warns(self):
        engine, buf = make_engine(self.TWO_LINES, autoplay=False,
                                  input_seq=["zzz", "", ""])
        engine.run()
        self.assertIn("命令无效", buf.getvalue())

    def test_eof_falls_into_auto_continue(self):
        # input_fn 持续抛 EOFError（管道到头）→ 应静默跑完而非卡死/崩溃
        engine, buf = make_engine(self.TWO_LINES, autoplay=False, input_seq=[])
        self.assertEqual(engine.run(), "结束")
        self.assertIn("two", buf.getvalue())


class TestDemoScriptIntegration(unittest.TestCase):
    """真实 demo 剧本 × 自动路线（全程第 1 项）集成测试。"""

    def setUp(self):
        from vn.script import Script
        self.script = Script.from_file(SAVE_SCRIPT)

    def run_autoplay(self):
        buf = io.StringIO()
        renderer = Renderer(stream=buf, color=False, cps=0)
        config = EngineConfig(autoplay=True, banner=False)
        engine = Engine(self.script, renderer=renderer, config=config)
        ending = engine.run()
        return ending, engine, buf.getvalue()

    def test_full_autoplay_route_reaches_true_end(self):
        ending, engine, text = self.run_autoplay()
        self.assertEqual(ending, "一起去看海")     # 真结局
        self.assertEqual(engine.state.affection, 6)
        self.assertEqual(engine.state.get("knows_truth"), 1)

    def test_autoplay_records_four_choices_and_history(self):
        ending, engine, _ = self.run_autoplay()
        choices = [h for h in engine.state.history if h.kind == "choice"]
        self.assertGreaterEqual(len(choices), 3)          # 至少 3 处分支
        scenes = [h.scene for h in engine.state.history if h.kind == "scene"]
        self.assertGreaterEqual(len(scenes), 4)           # 多场景切换
        self.assertEqual(engine.state.history[-1].kind, "ending")

    def run_with_picks(self, picks):
        """按分支顺序驱动交互：遇到「请选择」提示返回下一个策略项，否则回车。"""
        seq = iter(list(picks))
        buf = io.StringIO()
        renderer = Renderer(stream=buf, color=False, cps=0)
        config = EngineConfig(autoplay=False, banner=False)

        def input_fn(prompt):
            if "请选择" in prompt:
                try:
                    return next(seq)
                except StopIteration:
                    raise EOFError
            return ""

        engine = Engine(self.script, renderer=renderer, config=config,
                        input_fn=input_fn)
        ending = engine.run()
        return ending, engine

    def test_low_route_reaches_worst_end(self):
        # ①装没看见 ②离开 ③还票 ④沉默 → 好感度 -2 → 擦肩而过
        ending, engine = self.run_with_picks(["2", "3", "3", "2"])
        self.assertEqual(ending, "擦肩而过")
        self.assertLess(engine.state.affection, 1)
        self.assertEqual(engine.state.get("knows_truth"), 0)

    def test_mid_route_reaches_secondary_end(self):
        # ①递纸巾 ②小卖部 ③还票 ④看海 → 好感 6 但没走真相线 → 天台上的约定
        ending, engine = self.run_with_picks(["1", "2", "2", "1"])
        self.assertEqual(ending, "天台上的约定")
        self.assertEqual(engine.state.get("knows_truth"), 0)

    def test_hidden_first_option_absent_on_non_truth_route(self):
        # 非真相线时，天台分支的第 1 项（条件选项）不可见
        import io as _io
        from vn.script import Script as _Script
        from vn.render import Renderer as _Renderer
        buf = _io.StringIO()
        script = _Script.from_file(SAVE_SCRIPT)
        renderer = _Renderer(stream=buf, color=False, cps=0)
        config = EngineConfig(autoplay=False, banner=False)
        picks = iter(["2", "2", "2", "2"])

        def input_fn(prompt):
            if "请选择" in prompt:
                return next(picks, "1")
            return ""

        engine = Engine(script, renderer=renderer, config=config,
                        input_fn=input_fn)
        engine.run()
        # 分支③只在 knows_truth==1 时展示「我陪你一起找」
        self.assertNotIn("这次，我陪你一起找", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
