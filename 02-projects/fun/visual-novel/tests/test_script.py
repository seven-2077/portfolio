# -*- coding: utf-8 -*-
"""vn.script 解析器测试：行类型、注释/空行、错误报错、转义、标签与结局规则。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vn.script import (Choice, Comparison, Dialogue, End, EndingRule, If, Jump,
                       Label, Narration, Scene, ScriptError, SetVar, VarRef,
                       parse_condition, parse_script)


class TestDialogueAndNarration(unittest.TestCase):
    def test_parse_dialogue_line(self):
        s = parse_script("澪: 今天…你也在啊。")
        self.assertEqual(len(s.lines), 1)
        line = s.lines[0]
        self.assertIsInstance(line, Dialogue)
        self.assertEqual(line.speaker, "澪")
        self.assertEqual(line.text, "今天…你也在啊。")
        self.assertEqual(line.lineno, 1)

    def test_parse_dialogue_splits_on_first_colon(self):
        s = parse_script("广播: 紧急通知: 下雨了")
        self.assertEqual(s.lines[0].speaker, "广播")
        self.assertEqual(s.lines[0].text, "紧急通知: 下雨了")

    def test_parse_narration_line(self):
        s = parse_script("|窗外的雨还没有停。")
        self.assertIsInstance(s.lines[0], Narration)
        self.assertEqual(s.lines[0].text, "窗外的雨还没有停。")

    def test_comments_and_blank_lines_ignored(self):
        src = "# 开头注释\n\n   \n  # 缩进注释\n澪: 喂\n# 尾注释\n"
        s = parse_script(src)
        self.assertEqual(len(s.lines), 1)
        self.assertEqual(s.lines[0].speaker, "澪")

    def test_line_numbers_skip_comments(self):
        s = parse_script("# c\n\n|x\n\n\n澪: y")
        self.assertEqual(s.lines[0].lineno, 3)
        self.assertEqual(s.lines[1].lineno, 6)


class TestErrors(unittest.TestCase):
    def assert_error(self, src, fragment, lineno=None):
        with self.assertRaises(ScriptError) as ctx:
            parse_script(src, "bad.vn")
        self.assertIn(fragment, str(ctx.exception))
        if lineno is not None:
            self.assertEqual(ctx.exception.lineno, lineno)
        return ctx.exception

    def test_unknown_directive_reports_line(self):
        self.assert_error("|ok\n@fly away\n", "未知指令 @fly", lineno=2)

    def test_unrecognized_line_reports_line(self):
        self.assert_error("这行既不是指令也不是台词\n", "无法识别的行", lineno=1)

    def test_option_outside_choice_block(self):
        self.assert_error("- 选项A -> x\n", "@choice", lineno=1)

    def test_duplicate_label(self):
        self.assert_error("@label a\n@label a\n", "重复定义", lineno=2)

    def test_unknown_jump_target(self):
        self.assert_error("@jump nowhere\n", "不存在", lineno=1)

    def test_unknown_if_target(self):
        self.assert_error("@if a >= 1 -> nowhere\n", "不存在", lineno=1)

    def test_bad_set_format(self):
        self.assert_error("@set affection\n", "@set 格式错误", lineno=1)

    def test_if_missing_arrow(self):
        self.assert_error("@if affection >= 3\n", "->", lineno=1)

    def test_empty_choice_block(self):
        self.assert_error("@choice\n|x\n", "没有任何选项", lineno=1)

    def test_option_missing_arrow(self):
        self.assert_error("@choice\n- 没有目标\n", "->", lineno=2)

    def test_empty_script_rejected(self):
        self.assert_error("# 只有注释\n\n", "剧本为空")

    def test_dialogue_missing_speaker(self):
        self.assert_error("没有冒号的一行\n", "无法识别的行", lineno=1)

    def test_bad_condition_syntax(self):
        self.assert_error("@if affection @ 3 -> x\n", "格式错误", lineno=1)

    def test_trailing_backslash_error(self):
        self.assert_error("澪: 坏掉的转义\\", "孤立的反斜杠", lineno=1)

    def test_error_carries_source_name(self):
        with self.assertRaises(ScriptError) as ctx:
            parse_script("@nothing", "my_story.vn")
        self.assertIn("my_story.vn", str(ctx.exception))


class TestEscaping(unittest.TestCase):
    def test_escaped_colon_stays_in_text(self):
        s = parse_script("澪: 字条写着: for you。")
        self.assertEqual(s.lines[0].text, "字条写着: for you。")

    def test_escaped_backslash_and_newline(self):
        s = parse_script(r"澪: 双反斜杠 \\ 与 \n 换行")
        self.assertEqual(s.lines[0].text, "双反斜杠 \\ 与 \n 换行")

    def test_escaped_pipe_in_narration(self):
        s = parse_script(r"|一根竖线 \| 结束")
        self.assertEqual(s.lines[0].text, "一根竖线 | 结束")

    def test_scene_escapes_special_char(self):
        s = parse_script(r"@scene A\@B")
        self.assertIsInstance(s.lines[0], Scene)
        self.assertEqual(s.lines[0].title, "A@B")

    def test_unknown_escape_drops_backslash(self):
        s = parse_script(r"澪: \q 结果是 q")
        self.assertEqual(s.lines[0].text, "q 结果是 q")


class TestDirectives(unittest.TestCase):
    def test_set_ops_and_value_types(self):
        s = parse_script(
            "@set affection += 2\n@set flag = 1\n"
            '@set name = "澪"\n@set mood = 晴\n@set ok = true\n')
        ops = [(l.name, l.op, l.value) for l in s.lines]
        self.assertEqual(ops, [
            ("affection", "+=", 2), ("flag", "=", 1),
            ("name", "=", "澪"), ("mood", "=", "晴"), ("ok", "=", True)])

    def test_set_quoted_string_with_colon(self):
        s = parse_script('@set radio_label = "RAIN: 89.7"')
        self.assertEqual(s.lines[0].value, "RAIN: 89.7")

    def test_labels_map_to_line_indices(self):
        s = parse_script(
            "a: 1\n@label mid\nb: 2\n@label end_label\nc: 3\n")
        self.assertEqual(s.labels["mid"], 1)
        self.assertEqual(s.labels["end_label"], 3)
        self.assertIsInstance(s.lines[1], Label)
        self.assertEqual(s.lines[1].name, "mid")

    def test_choice_options_parsed_with_condition(self):
        s = parse_script(
            "@choice\n"
            "- [affection >= 3 and flag == 1] 拉她走 -> go\n"
            "- 留下 -> stay\n")
        choice = s.lines[0]
        self.assertIsInstance(choice, Choice)
        self.assertEqual(len(choice.options), 2)
        first = choice.options[0]
        self.assertEqual(first.text, "拉她走")
        self.assertEqual(first.label, "go")
        self.assertIsNotNone(first.condition)
        # 条件结构：Comparison and Comparison
        self.assertIsInstance(first.condition.tokens[0], Comparison)
        self.assertEqual(first.condition.tokens[1], "and")
        self.assertIsInstance(first.condition.tokens[2], Comparison)
        self.assertIsNone(choice.options[1].condition)

    def test_choice_block_closes_before_next_line(self):
        s = parse_script("@choice\n- A -> a\n- B -> b\n|之后是旁白\n")
        self.assertIsInstance(s.lines[0], Choice)
        self.assertIsInstance(s.lines[1], Narration)

    def test_if_line_parses_condition_and_label(self):
        s = parse_script("@if affection >= 3 -> warm\n@label warm\nx: 1\n")
        line = s.lines[0]
        self.assertIsInstance(line, If)
        self.assertEqual(line.label, "warm")
        self.assertEqual(line.condition.tokens[0].var, "affection")
        self.assertEqual(line.condition.tokens[0].op, ">=")
        self.assertEqual(line.condition.tokens[0].value, 3)

    def test_jump_and_end_lines(self):
        s = parse_script("@label t\n@jump t\n@end 一起去看海\n@end\n")
        self.assertIsInstance(s.lines[1], Jump)
        self.assertEqual(s.lines[2].ending, "一起去看海")
        self.assertIsNone(s.lines[3].ending)

    def test_fx_directives(self):
        s = parse_script("@sfx radio\n@bgm theme\n@anim shake\n")
        kinds = [(l.kind, l.name) for l in s.lines]
        self.assertEqual(kinds, [("sfx", "radio"), ("bgm", "theme"), ("anim", "shake")])


class TestConditionParser(unittest.TestCase):
    def test_compare_ops(self):
        cond = parse_condition("affection >= 5")
        self.assertEqual(cond.tokens[0].op, ">=")

    def test_and_or_tokens(self):
        cond = parse_condition("a == 1 or b == 2 and c != 3")
        self.assertEqual(cond.tokens[1], "or")
        self.assertEqual(cond.tokens[3], "and")

    def test_varref_on_rhs(self):
        cond = parse_condition("affection >= mood")
        self.assertIsInstance(cond.tokens[0].value, VarRef)
        self.assertEqual(cond.tokens[0].value.name, "mood")

    def test_quoted_string_rhs(self):
        cond = parse_condition('mood == "晴"')
        self.assertEqual(cond.tokens[0].value, "晴")

    def test_error_leading_and(self):
        with self.assertRaises(ScriptError):
            parse_condition("and a >= 1")

    def test_error_trailing_or(self):
        with self.assertRaises(ScriptError):
            parse_condition("a >= 1 or")

    def test_error_empty(self):
        with self.assertRaises(ScriptError):
            parse_condition("   ")


class TestEndingRules(unittest.TestCase):
    def test_ending_rules_parsed_in_order(self):
        s = parse_script(
            "@ending 真结局 when affection >= 5\n"
            "@ending 普通 when affection >= 2\n"
            "|body\n@end\n")
        self.assertEqual(len(s.endings), 2)
        self.assertIsInstance(s.endings[0], EndingRule)
        self.assertEqual(s.endings[0].name, "真结局")
        self.assertEqual(s.endings[1].name, "普通")

    def test_ending_requires_when(self):
        with self.assertRaises(ScriptError):
            parse_script("@ending 裸名\n")

    def test_if_missing_label_target(self):
        with self.assertRaises(ScriptError):
            parse_script("@if a >= 1 -> \n")


if __name__ == "__main__":
    unittest.main()
