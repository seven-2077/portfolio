"""关卡：JSON 加载、结构合法性校验（重叠/悬空/材质/边界）。"""
import json
import unittest
from pathlib import Path

from game import level as lvl

LEVELS_DIR = Path(__file__).resolve().parent.parent / "levels"


def base_data() -> dict:
    return {
        "name": "单元测试关",
        "world": {"width": 96, "height": 32, "gravity": 30},
        "ground_y": 28,
        "sling": [10, 24],
        "ammo": 3,
        "blocks": [{"x": 60, "y": 27.5, "w": 2, "h": 1, "material": "wood"}],
    }


class TestLevelLoading(unittest.TestCase):
    def test_three_levels_load_and_are_valid(self):
        specs = lvl.load_all()
        self.assertEqual(len(specs), 3)
        self.assertEqual([s.index for s in specs], [1, 2, 3])
        for spec in specs:
            self.assertGreaterEqual(spec.total_blocks, 7)
            self.assertGreaterEqual(spec.par, 1)

    def test_raw_json_files_pass_validation(self):
        files = sorted(LEVELS_DIR.glob("level*.json"))
        self.assertEqual(len(files), 3)
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(lvl.validate(data), [], f"{f.name} 应合法")

    def test_missing_file_raises(self):
        with self.assertRaises(lvl.LevelError):
            lvl.load(LEVELS_DIR / "nope99.json")


class TestValidationRejects(unittest.TestCase):
    def _errors(self, mutate) -> list[str]:
        data = base_data()
        mutate(data)
        return lvl.validate(data)

    def test_valid_data_passes(self):
        self.assertEqual(lvl.validate(base_data()), [])

    def test_overlap_rejected(self):
        def m(d):
            d["blocks"].append({"x": 60.5, "y": 27.5, "w": 2, "h": 1, "material": "stone"})

        errs = self._errors(m)
        self.assertTrue(any("重叠" in e for e in errs), errs)

    def test_floating_block_rejected(self):
        def m(d):
            d["blocks"] = [{"x": 60, "y": 20, "w": 2, "h": 1, "material": "wood"}]

        errs = self._errors(m)
        self.assertTrue(any("悬空" in e for e in errs), errs)

    def test_unknown_material_rejected(self):
        def m(d):
            d["blocks"][0]["material"] = "bamboo"

        errs = self._errors(m)
        self.assertTrue(any("未知材质" in e for e in errs), errs)

    def test_block_below_ground_rejected(self):
        def m(d):
            d["blocks"] = [{"x": 60, "y": 30, "w": 2, "h": 1, "material": "wood"}]

        errs = self._errors(m)
        self.assertTrue(any("越过地面线" in e for e in errs), errs)

    def test_empty_blocks_rejected(self):
        errs = self._errors(lambda d: d.update(blocks=[]))
        self.assertTrue(any("非空" in e for e in errs), errs)

    def test_zero_ammo_rejected(self):
        errs = self._errors(lambda d: d.update(ammo=0))
        self.assertTrue(any("ammo" in e for e in errs), errs)

    def test_sling_out_of_world_rejected(self):
        errs = self._errors(lambda d: d.update(sling=[200, 24]))
        self.assertTrue(any("弹弓锚点" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
