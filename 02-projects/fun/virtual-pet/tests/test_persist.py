"""存档往返、缺失回退、损坏备份与坏值夹取。"""

import json
import tempfile
import unittest
from pathlib import Path

from pet import engine, persist


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "deep" / "pet.json"
        self.addCleanup(self._tmp.cleanup)

    def test_save_load_roundtrip(self):
        pet = engine.new_pet("圆圆", now=123456.0)
        pet.hunger, pet.mood, pet.energy, pet.health = 12.5, 44, 33, 77
        pet.age_seconds, pet.stage_idx = 999.5, 2
        pet.status, pet.sleep_left = engine.SLEEPING, 500
        pet.stress_seconds, pet.grow_warned = 55.5, True
        pet.sick_noted, pet.last_tick = True, 123999.0
        saved = persist.save(pet, self.path)
        self.assertTrue(saved.exists())
        loaded = persist.load(self.path)
        self.assertEqual(loaded, pet)

    def test_load_missing_returns_none(self):
        self.assertIsNone(persist.load(Path(self._tmp.name) / "nope.json"))


class TestCorruptFallback(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "pet.json"
        self.addCleanup(self._tmp.cleanup)

    def test_broken_json_returns_none_and_backs_up(self):
        self.path.write_text("{ 坏掉的 json;;;", encoding="utf-8")
        self.assertIsNone(persist.load(self.path))          # 不抛异常
        backup = self.path.with_suffix(self.path.suffix + ".corrupt")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_text(encoding="utf-8"),
                         "{ 坏掉的 json;;;")                # 原文留证

    def test_non_dict_json_returns_none(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(persist.load(self.path))
        self.assertTrue(self.path.with_suffix(".json.corrupt").exists())


class TestHydration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "pet.json"
        self.addCleanup(self._tmp.cleanup)

    def _write(self, payload):
        self.path.write_text(json.dumps(payload, ensure_ascii=False),
                             encoding="utf-8")

    def test_partial_fields_fall_back_to_defaults(self):
        self._write({"name": "半档", "mood": 42})
        pet = persist.load(self.path)
        self.assertEqual(pet.name, "半档")
        self.assertEqual(pet.mood, 42)
        self.assertEqual(pet.hunger, 30)          # 缺字段用默认
        self.assertEqual(pet.status, "idle")
        self.assertFalse(pet.sick_noted)

    def test_out_of_range_values_clamped(self):
        self._write({"hunger": 250, "mood": -5, "stage_idx": 9,
                     "status": "flying", "age_seconds": -10,
                     "stress_seconds": -3})
        pet = persist.load(self.path)
        self.assertEqual(pet.hunger, 100)
        self.assertEqual(pet.mood, 0)
        self.assertEqual(pet.stage_idx, 3)
        self.assertEqual(pet.status, "idle")
        self.assertEqual(pet.age_seconds, 0)
        self.assertEqual(pet.stress_seconds, 0)

    def test_wrong_types_ignored(self):
        self._write({"mood": "happy", "stage_idx": "two",
                     "grow_warned": 1, "name": 42})
        pet = persist.load(self.path)
        self.assertEqual(pet.mood, 70)            # 回到默认
        self.assertEqual(pet.stage_idx, 0)
        self.assertFalse(pet.grow_warned)
        self.assertEqual(pet.name, "小煤球")


if __name__ == "__main__":
    unittest.main()
