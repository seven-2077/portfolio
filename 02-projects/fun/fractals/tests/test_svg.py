"""SVG 输出测试：XML 可解析、线段数一致、空集合合法。"""
import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from fractals.svg_turtle import segments_to_svg, svg_line_count, write_svg
from fractals.turtle import Segment

NS = "{http://www.w3.org/2000/svg}"

SEGMENTS = [
    Segment(0.0, 0.0, 1.0, 0.0),
    Segment(1.0, 0.0, 1.0, 1.0),
    Segment(1.0, 1.0, 0.0, 1.0),
]


class TestSegmentsToSvg(unittest.TestCase):
    def test_parses_as_xml(self):
        svg = segments_to_svg(SEGMENTS)
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, f"{NS}svg")

    def test_line_count_matches_segments(self):
        svg = segments_to_svg(SEGMENTS)
        self.assertEqual(svg_line_count(svg), len(SEGMENTS))

    def test_line_coordinates_within_viewbox(self):
        svg = segments_to_svg(SEGMENTS, width=400, height=300, margin=0.1)
        root = ET.fromstring(svg)
        for line in root.iter(f"{NS}line"):
            for attr, limit in (("x1", 400), ("x2", 400),
                                ("y1", 300), ("y2", 300)):
                v = float(line.get(attr))
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, limit)

    def test_empty_segments_valid_document(self):
        svg = segments_to_svg([])
        root = ET.fromstring(svg)
        self.assertEqual(svg_line_count(svg), 0)
        self.assertIsNotNone(root.find(f"{NS}rect"))       # 背景仍存在

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            segments_to_svg(SEGMENTS, width=0)
        with self.assertRaises(ValueError):
            segments_to_svg(SEGMENTS, stroke_width=0)


class TestWriteSvg(unittest.TestCase):
    def test_write_then_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.svg")
            write_svg(path, SEGMENTS, width=200, height=200)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            root = ET.fromstring(text)
            self.assertEqual(root.tag, f"{NS}svg")
            self.assertEqual(svg_line_count(text), 3)
            self.assertTrue(text.lstrip().startswith("<svg"))


if __name__ == "__main__":
    unittest.main()
