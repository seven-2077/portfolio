"""渲染：终端字符画布局 + SVG 结果帧可解析。"""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from game import level as lvl
from game.render import PROJ_CHAR, TerminalRenderer, export_svg
from game.sling import Slingshot
from game.world import World

ROOT = Path(__file__).resolve().parent.parent
SVG_NS = "{http://www.w3.org/2000/svg}"


def hud_dict(**over) -> dict:
    base = {
        "level": 1,
        "name": "塔楼",
        "score": 0,
        "ammo_left": 3,
        "ammo_total": 3,
        "broken": 0,
        "total": 7,
        "rate": 0.0,
        "status": "待命",
        "aim": None,
    }
    base.update(over)
    return base


class TestTerminalFrame(unittest.TestCase):
    def setUp(self):
        self.spec = lvl.load_all()[0]
        self.world = World(self.spec)
        self.renderer = TerminalRenderer(self.world)

    def test_frame_layout_and_entities(self):
        frame = self.renderer.draw(hud_dict())
        lines = frame.splitlines()
        self.assertEqual(len(lines), self.renderer.rows + 2)  # 2 行 HUD + 字符网格
        self.assertIn("关卡1", lines[0])
        self.assertIn("●●●", lines[0])
        self.assertIn("▒", frame)  # 木块
        self.assertIn("░", frame)  # 玻璃
        self.assertTrue(any("=" in ln for ln in lines), "地面行应存在")

    def test_held_projectile_and_bands_drawn(self):
        Slingshot(self.world).hold(55, 0.85)
        frame = self.renderer.draw(hud_dict(status="拉弓", aim=(55, 0.85)))
        self.assertIn(PROJ_CHAR, frame)
        self.assertIn("瞄准 55° 85%", frame)

    def test_ammo_bullets_show_usage(self):
        frame = self.renderer.draw(hud_dict(ammo_left=1, ammo_total=3))
        self.assertIn("●○○", frame)


class TestSvgExport(unittest.TestCase):
    tmp = ROOT / "output" / "_test_tmp.svg"

    def setUp(self):
        spec = lvl.load(index=1)
        self.world = World(spec)
        sling = Slingshot(self.world)
        sling.release(52, 0.92)  # 打一发产生碎块与轨迹
        while self.world.shot_active:
            self.world.step()
        self.world.settle()

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def _export(self) -> ET.Element:
        export_svg(
            self.world,
            self.tmp,
            title="测试关卡 <废墟>",
            score_line="得分 100",
            subtitle="unit",
        )
        return ET.parse(self.tmp).getroot()

    def test_svg_is_parseable_xml(self):
        root = self._export()
        self.assertEqual(root.tag, f"{SVG_NS}svg")
        self.assertEqual(root.get("viewBox"), "0 0 2112 704")

    def test_svg_contains_structure_and_effects(self):
        self._export()
        tree = ET.parse(self.tmp)
        rects = tree.findall(f".//{SVG_NS}rect")
        polylines = tree.findall(f".//{SVG_NS}polyline")
        circles = tree.findall(f".//{SVG_NS}circle")
        texts = tree.findall(f".//{SVG_NS}text")
        self.assertGreaterEqual(len(rects), 5)  # 天空+地面+图例+残存方块
        self.assertGreaterEqual(len(polylines), 1)  # 飞行轨迹
        self.assertGreaterEqual(len(circles), 1)  # 碎块/弹丸
        self.assertGreaterEqual(len(texts), 2)  # 标题与得分

    def test_svg_writes_only_into_output(self):
        self._export()
        self.assertTrue(self.tmp.is_relative_to(ROOT / "output"))


if __name__ == "__main__":
    unittest.main()
