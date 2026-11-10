# -*- coding: utf-8 -*-
"""vn.state 测试：变量/好感度、条件求值（含 and/or 与变量右值）、存档读档、历史。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vn.script import parse_condition, parse_script
from vn.state import (HISTORY_LIMIT, HistoryEntry, SaveError, State,
                      StateError, evaluate_condition)


def cond(text):
    return parse_condition(text)


class TestVariables(unittest.TestCase):
    def test_undefined_var_returns_zero(self):
        st = State()
        self.assertEqual(st.get("affection"), 0)
        self.assertEqual(st.affection, 0)

    def test_set_and_apply_ops(self):
        st = State()
        st.apply("affection", "+=", 2)
        st.apply("affection", "+=", 3)
        st.apply("affection", "-=", 1)
        st.apply("flag", "=", 1)
        self.assertEqual(st.affection, 4)
        self.assertEqual(st.get("flag"), 1)

    def test_apply_non_numeric_raises(self):
        st = State()
        st.apply("name", "=", "澪")
        with self.assertRaises(StateError):
            st.apply("name", "+=", 1)

    def test_set_rejects_unserializable(self):
        st = State()
        with self.assertRaises(StateError):
            st.set("bad", {"nested": True})

    def test_affection_setter(self):
        st = State()
        st.affection = 7
        self.assertEqual(st.variables["affection"], 7)


class TestConditions(unittest.TestCase):
    def test_compare_all_ops(self):
        variables = {"a": 5, "b": 5, "c": 3, "s": "晴"}
        cases = [
            ("a == 5", True), ("a != 5", False), ("a >= 5", True),
            ("a > 5", False), ("c < 5", True), ("a <= 4", False),
            ('s == "晴"', True), ('s == "雨"', False),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(evaluate_condition(cond(text), variables), expected)

    def test_undefined_var_defaults_zero(self):
        self.assertTrue(evaluate_condition(cond("ghost >= 0"), {}))
        self.assertFalse(evaluate_condition(cond("ghost >= 1"), {}))

    def test_and_or_precedence(self):
        # a or b and c : and 先算 -> a or (b and c)
        variables = {"a": 0, "b": 0, "c": 0}
        self.assertFalse(evaluate_condition(cond("a == 1 or b == 1 and c == 1"), variables))
        variables = {"a": 1, "b": 0, "c": 0}
        self.assertTrue(evaluate_condition(cond("a == 1 or b == 1 and c == 1"), variables))

    def test_and_requires_all(self):
        variables = {"affection": 3, "flag": 0}
        self.assertFalse(evaluate_condition(
            cond("affection >= 3 and flag == 1"), variables))
        variables["flag"] = 1
        self.assertTrue(evaluate_condition(
            cond("affection >= 3 and flag == 1"), variables))

    def test_rhs_variable_reference(self):
        variables = {"affection": 4, "mood": 2}
        self.assertTrue(evaluate_condition(cond("affection >= mood"), variables))
        self.assertFalse(evaluate_condition(cond("affection < mood"), variables))

    def test_mixed_type_compare_is_false_not_crash(self):
        variables = {"name": "澪"}
        self.assertFalse(evaluate_condition(cond('name >= 1'), variables))
        self.assertTrue(evaluate_condition(cond('name != 1'), variables))

    def test_satisfies_none_is_true(self):
        self.assertTrue(State().satisfies(None))

    def test_condition_from_script_block(self):
        # 走一遍 @if 的完整解析链
        s = parse_script("@if affection >= 1 and knows_truth == 1 -> t\n@label t\nx: 1\n")
        st = State(variables={"affection": 1, "knows_truth": 1})
        self.assertTrue(st.satisfies(s.lines[0].condition))
        st2 = State(variables={"affection": 1})
        self.assertFalse(st2.satisfies(s.lines[0].condition))


class TestSaveLoad(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.save_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_state(self):
        st = State(script_name="rain_signal", line_index=12, scene="天台")
        st.set("affection", 5)
        st.set("knows_truth", True)
        st.set("radio_label", "RAIN: 89.7")
        st.record(HistoryEntry("line", speaker="澪", text="……你也来啦。", scene="天台"))
        st.record(HistoryEntry("choice", choice={"index": 1, "text": "拉她走"}))
        return st

    def test_roundtrip_preserves_everything(self):
        st = self.make_state()
        st.save_to(1, self.save_dir)
        loaded = State.load_from(1, self.save_dir, expect_script="rain_signal")
        self.assertEqual(loaded.line_index, 12)
        self.assertEqual(loaded.scene, "天台")
        self.assertEqual(loaded.variables, st.variables)
        self.assertEqual(len(loaded.history), 2)
        self.assertEqual(loaded.history[0].speaker, "澪")
        self.assertEqual(loaded.history[1].choice["text"], "拉她走")
        self.assertEqual(loaded.affection, 5)
        self.assertTrue(loaded.get("knows_truth"))

    def test_multi_slot_isolation(self):
        a = self.make_state()
        a.save_to(1, self.save_dir)
        b = State(script_name="rain_signal", line_index=99, scene="校门")
        b.set("affection", 0)
        b.save_to(2, self.save_dir)
        self.assertEqual(State.load_from(1, self.save_dir).line_index, 12)
        self.assertEqual(State.load_from(2, self.save_dir).line_index, 99)
        slots = State.list_slots(self.save_dir)
        self.assertEqual([s["slot"] for s in slots], [1, 2])

    def test_save_is_valid_utf8_json(self):
        self.make_state().save_to(3, self.save_dir)
        data = json.loads(State.slot_path(3, self.save_dir).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["variables"]["radio_label"], "RAIN: 89.7")
        self.assertIn("saved_at", data)

    def test_load_empty_slot_raises(self):
        with self.assertRaises(SaveError):
            State.load_from(9, self.save_dir)

    def test_load_wrong_script_raises(self):
        self.make_state().save_to(1, self.save_dir)
        with self.assertRaises(SaveError):
            State.load_from(1, self.save_dir, expect_script="other_script")

    def test_corrupted_save_raises(self):
        path = State.slot_path(5, self.save_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken json", encoding="utf-8")
        with self.assertRaises(SaveError):
            State.load_from(5, self.save_dir)

    def test_invalid_slot_number_raises(self):
        with self.assertRaises(SaveError):
            State.slot_path(0, self.save_dir)


class TestHistory(unittest.TestCase):
    def test_history_entry_roundtrip(self):
        e = HistoryEntry("choice", choice={"index": 2, "text": "留下"},
                         scene="教室", lineno=8)
        again = HistoryEntry.from_dict(e.to_dict())
        self.assertEqual(again, e)

    def test_history_capped_at_limit(self):
        st = State()
        for i in range(HISTORY_LIMIT + 50):
            st.record(HistoryEntry("line", text=str(i)))
        self.assertEqual(len(st.history), HISTORY_LIMIT)
        self.assertEqual(st.history[-1].text, str(HISTORY_LIMIT + 49))

    def test_state_rejects_future_version(self):
        with self.assertRaises(SaveError):
            State.from_dict({"version": 999, "script": "x"})


if __name__ == "__main__":
    unittest.main()
