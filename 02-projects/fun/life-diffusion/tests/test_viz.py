"""可视化测试：终端固定帧数、SVG 结构可被 XML 解析。"""

import io
import unittest
import xml.etree.ElementTree as ET

from lifelab.game_of_life import GameOfLife
from lifelab.patterns import get_pattern
from lifelab.viz import (
    animate,
    field_atlas_svg,
    field_snapshot_svg,
    life_strip_svg,
    render_life_text,
)

NS = "{http://www.w3.org/2000/svg}"


def _rects(root: ET.Element) -> list[ET.Element]:
    return root.findall(f".//{NS}rect")


class TestTerminal(unittest.TestCase):
    def test_render_life_text_dimensions(self):
        life = GameOfLife(4, 3, [(0, 0)])
        text = render_life_text(life.live_cells, 4, 3)
        lines = text.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(lines[0]), 8)  # 4 格 × 双宽字符
        self.assertTrue(lines[0].startswith("\u2588\u2588"))
        self.assertEqual(lines[1].strip(), "")

    def test_animate_fixed_frame_count(self):
        buf = io.StringIO()
        life = GameOfLife(20, 10)
        life.add(get_pattern("glider").cells_at((1, 1)))
        frames = animate(life, steps=20, delay=0.0, out=buf, clear=False)
        self.assertEqual(frames, 21)  # 固定帧数：初始帧 + 20 步
        text = buf.getvalue()
        self.assertEqual(text.count("gen "), 21)
        self.assertIn("population = 5", text)  # 每帧带代数与人口题头
        self.assertEqual(life.generation, 20)
        self.assertEqual(life.population, 5)

    def test_animate_clear_writes_ansi(self):
        buf = io.StringIO()
        life = GameOfLife(6, 6, [(1, 1)])
        animate(life, steps=1, delay=0.0, out=buf, clear=True)
        self.assertIn("\x1b[2J", buf.getvalue())

    def test_animate_negative_raises(self):
        with self.assertRaises(ValueError):
            animate(GameOfLife(4, 4), steps=-1, delay=0.0, out=io.StringIO())


class TestLifeSvg(unittest.TestCase):
    def test_single_frame_strip_parses(self):
        # 单帧胶片 = 单帧快照
        life = GameOfLife(6, 4, [(0, 0), (1, 1)])
        svg = life_strip_svg([life], cell=5, labels=["gen 0"])
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, f"{NS}svg")
        self.assertEqual(root.get("width"), str(6 * 5 + 2 * 12))
        self.assertGreaterEqual(len(_rects(root)), 3)  # 背景 + 面板 + 活细胞

    def test_strip_grid_path_per_panel(self):
        base = GameOfLife(3, 3, [(1, 1)])
        frames = [base.copy() for _ in range(2)]
        root = ET.fromstring(life_strip_svg(frames, cell=4))
        self.assertEqual(len(root.findall(f".//{NS}path")), 2)

    def test_strip_parses_with_panels_and_labels(self):
        base = GameOfLife(6, 4, [(0, 0), (1, 1)])
        frames = [base.copy() for _ in range(3)]
        frames[1].step()
        svg = life_strip_svg(frames, labels=["gen 0", "gen 4", "gen 8"], title="t & x")
        root = ET.fromstring(svg)  # & 已转义，否则这里就抛
        texts = root.findall(f".//{NS}text")
        self.assertEqual(len(texts), 4)  # 3 帧题注 + 标题
        self.assertEqual(texts[0].text, "gen 0")

    def test_strip_empty_raises(self):
        with self.assertRaises(ValueError):
            life_strip_svg([])


class TestFieldSvg(unittest.TestCase):
    def setUp(self):
        self.w, self.h = 8, 6
        self.field = tuple((i % 10) / 10 for i in range(self.w * self.h))

    def test_gray_mode_parses(self):
        svg = field_snapshot_svg(self.field, self.w, self.h, scale=3, mode="gray")
        root = ET.fromstring(svg)
        self.assertEqual(root.get("width"), str(self.w * 3))
        self.assertGreater(len(_rects(root)), 1)

    def test_duo_mode_parses(self):
        svg = field_snapshot_svg(
            self.field, self.w, self.h, scale=2, mode="duo", label="斑点 gen 600"
        )
        root = ET.fromstring(svg)
        self.assertEqual(root.get("height"), str(self.h * 2 + 18))
        self.assertGreater(len(_rects(root)), 1)

    def test_constant_field_does_not_crash(self):
        flat = tuple([0.0] * (self.w * self.h))
        root = ET.fromstring(field_snapshot_svg(flat, self.w, self.h, mode="gray"))
        self.assertEqual(root.get("width"), str(self.w * 4))

    def test_invalid_mode_and_length_raise(self):
        with self.assertRaises(ValueError):
            field_snapshot_svg(self.field, self.w, self.h, mode="rainbow")
        with self.assertRaises(ValueError):
            field_snapshot_svg(self.field[:5], self.w, self.h)

    def test_label_escaped(self):
        svg = field_snapshot_svg(self.field, self.w, self.h, label="a & b <c>")
        root = ET.fromstring(svg)  # 转义失败会抛 ParseError
        self.assertIn("&amp;", svg)

    def test_atlas_parses_and_sizes(self):
        panels = [(self.field, self.w, self.h, f"p{i}") for i in range(3)]
        svg = field_atlas_svg(panels, columns=3, scale=2, mode="duo")
        root = ET.fromstring(svg)
        # 3 面板 × (1 背景 rect + 游程 rect) + 图集背景
        self.assertGreaterEqual(len(_rects(root)), 4)
        self.assertEqual(root.get("width"), str(3 * (self.w * 2) + 4 * 14))
        self.assertEqual(len(root.findall(f".//{NS}text")), 3)

    def test_atlas_rejects_mismatched_panels(self):
        panels = [(self.field, 8, 6, "a"), (self.field, 4, 4, "b")]
        with self.assertRaises(ValueError):
            field_atlas_svg(panels)
        with self.assertRaises(ValueError):
            field_atlas_svg([])


if __name__ == "__main__":
    unittest.main()
