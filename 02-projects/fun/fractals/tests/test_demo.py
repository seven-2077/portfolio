"""demo.py 冒烟测试：只校验配置与可导入性，不重跑全量出图。"""
import unittest

import demo


class TestDemoConfig(unittest.TestCase):
    def test_julia_presets_count_and_names(self):
        """c 参数扫描图集必须有 4 个预设 c，且名字互不重复。"""
        self.assertEqual(len(demo.JULIA_PRESETS), 4)
        names = [name for name, _ in demo.JULIA_PRESETS]
        self.assertEqual(len(set(names)), 4)
        for _, c in demo.JULIA_PRESETS:
            self.assertIsInstance(c, complex)

    def test_output_dir_inside_project(self):
        """产物目录固定在项目内 output/（项目隔离硬约束）。"""
        self.assertTrue(demo.OUTPUT_DIR.endswith("output"))
        self.assertIn("fractals", demo.OUTPUT_DIR)

    def test_main_callable(self):
        self.assertTrue(callable(demo.main))


if __name__ == "__main__":
    unittest.main()
