"""svg_out.py 单元测试：三张 SVG 的 XML 合法性、关键元素与落盘。"""

from __future__ import annotations

import shutil
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from pendulum import trace
from viz import svg_out

BASE = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)

# 产物只写项目内 output/ 下的临时目录，tearDown 即删
_TMP_ROOT = Path(__file__).resolve().parents[1] / "output" / "_test_tmp"


class SvgTestBase(unittest.TestCase):
    pair = None  # 类级共享，避免每个用例重跑仿真

    @classmethod
    def setUpClass(cls):
        state_b = (BASE[0] + 1e-4,) + BASE[1:]
        cls.pair = trace.run_pair(BASE, state_b, t_end=3.0, dt=1e-3)

    def setUp(self):
        self.tmp = _TMP_ROOT / uuid.uuid4().hex
        self.tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _parse(self, name: str) -> ET.Element:
        tree = ET.parse(self.tmp / name)
        return tree.getroot()


class TestTrajectorySvg(SvgTestBase):
    def test_wellformed_svg_with_two_colors(self):
        p = self.tmp / svg_out.TRAJECTORY_FILE
        p.write_text(svg_out.trajectory_svg(self.pair), encoding="utf-8")
        root = self._parse(svg_out.TRAJECTORY_FILE)
        self.assertTrue(root.tag.endswith("svg"))
        text = p.read_text(encoding="utf-8")
        self.assertIn(svg_out.COLOR_A, text)   # 初值 A 红色
        self.assertIn(svg_out.COLOR_B, text)   # 初值 B 青色
        self.assertIn("polyline", text)        # 轨迹曲线存在
        self.assertIn("1e-4", text)            # 图例标注了 Δθ

    def test_time_gradient_opacities_present(self):
        """随时间渐变：应存在多个不同 stroke-opacity 的轨迹段。"""
        text = svg_out.trajectory_svg(self.pair)
        opacities = set()
        for token in text.split('stroke-opacity="'):
            if '"' in token:
                opacities.add(token.split('"')[0])
        self.assertGreater(len(opacities), 5,
                           f"透明度阶梯只有 {len(opacities)} 级，渐变不明显")


class TestEnergySvg(SvgTestBase):
    def test_wellformed_with_drift_legend(self):
        p = self.tmp / svg_out.ENERGY_FILE
        p.write_text(svg_out.energy_svg(self.pair), encoding="utf-8")
        root = self._parse(svg_out.ENERGY_FILE)
        self.assertTrue(root.tag.endswith("svg"))
        text = p.read_text(encoding="utf-8")
        self.assertIn("max|ΔE|", text)
        self.assertIn(svg_out.COLOR_A, text)
        self.assertIn(svg_out.COLOR_B, text)
        self.assertIn("时间 t (s)", text)


class TestDivergenceSvg(SvgTestBase):
    def test_wellformed_with_bifurcation_marker(self):
        p = self.tmp / svg_out.DIVERGENCE_FILE
        p.write_text(svg_out.divergence_svg(self.pair, threshold=0.1), encoding="utf-8")
        root = self._parse(svg_out.DIVERGENCE_FILE)
        self.assertTrue(root.tag.endswith("svg"))
        text = p.read_text(encoding="utf-8")
        self.assertIn("分岔 t*", text)          # 竖线标注分岔时刻
        self.assertIn("阈值 0.1", text)          # 阈值参考线
        self.assertIn("log", text.lower())

    def test_identical_runs_render_gracefully(self):
        """对照组（距离恒 0）不能崩，应给出说明而不是画 log(0)。"""
        same = trace.run_pair(BASE, BASE, t_end=0.5, dt=1e-3)
        text = svg_out.divergence_svg(same, threshold=0.1)
        self.assertIn("完全重合", text)


class TestWriteAll(SvgTestBase):
    def test_write_all_creates_three_files(self):
        paths = svg_out.write_all(self.pair, self.tmp, threshold=0.1)
        self.assertEqual(len(paths), 3)
        for p in paths:
            self.assertTrue(p.exists())
            self.assertGreater(p.stat().st_size, 1000)
            self._parse(p.name)  # 逐个解析验证


if __name__ == "__main__":
    unittest.main()
