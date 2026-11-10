"""SVG 星图测试：可解析、结构完整、可选标题、落盘。"""

import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from orbit.chart import PLANET_STYLE, build_chart, save_chart
from orbit.time_utils import datetime_to_jd

_JD = datetime_to_jd(datetime(2026, 6, 9, 12))
_SVG_NS = "{http://www.w3.org/2000/svg}"


class TestSvgStructure(unittest.TestCase):
    def test_svg_parses(self):
        """整段 SVG 能被标准 XML 解析器解析，根节点是 svg。"""
        svg = build_chart(_JD)
        root = ET.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(root.get("viewBox"), "0 0 760 760")

    def test_contains_twelve_signs_and_planets(self):
        """含十二宫标签与七颗行星 + 太阳的标记。"""
        svg = build_chart(_JD)
        for sign in ("白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
                     "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼"):
            self.assertIn(sign, svg, f"缺少宫位标签 {sign}")
        for name, _sym, _color in PLANET_STYLE.values():
            self.assertIn(name, svg, f"缺少行星标记 {name}")
        self.assertIn("太阳", svg)

    def test_contains_date_title_by_default(self):
        """默认标题包含日期；结构上 title 为可选参数。"""
        self.assertIn("2026-06-09", build_chart(_JD))

    def test_custom_and_hidden_title(self):
        self.assertIn("自定义标题", build_chart(_JD, title="自定义标题"))
        self.assertNotIn("黄道星图 ·", build_chart(_JD, title=""))

    def test_root_children_count(self):
        """背景、扇形、圆、文本等元素数量充足（不是空壳）。"""
        root = ET.fromstring(build_chart(_JD))
        children = list(root)
        self.assertGreater(len(children), 60)
        circles = [c for c in children if c.tag == f"{_SVG_NS}circle"]
        self.assertGreaterEqual(len(circles), 10)  # 12 宫带外圆 + 行星/太阳


class TestSaveChart(unittest.TestCase):
    def test_save_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "test.svg"
            result = save_chart(_JD, path)
            self.assertEqual(result, path)
            self.assertTrue(path.is_file())
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("<?xml"))
            ET.fromstring(content)  # 落盘后仍可解析

    def test_output_dir_default_exists_after_demo(self):
        """output/ 目录约定由 save_chart 自动创建（这里验证可建子目录）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output" / "zodiac.svg"
            save_chart(_JD, path)
            self.assertTrue(path.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
