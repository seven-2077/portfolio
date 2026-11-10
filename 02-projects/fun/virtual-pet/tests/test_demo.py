"""demo：时间加速主流程 + BMP 快照图输出。"""

import struct
import tempfile
import unittest
from pathlib import Path

import demo


class TestSimulate(unittest.TestCase):
    def test_short_simulation_smoke(self):
        lines = []
        pet = demo.simulate(steps=4, out=lines.append)
        joined = "\n".join(lines)
        self.assertIn("时间加速", joined)
        self.assertIn("virtual-pet", joined)
        self.assertGreater(pet.age_seconds, 0)     # 虚拟时间已推进
        self.assertLess(pet.hunger, 30)            # 第 1 步喂食 → 饱食↑

    def test_log_written_to_output_dir(self):
        demo.simulate(steps=2, out=lambda *_: None)
        self.assertTrue(demo.LOG_FILE.exists())
        self.assertIn("模拟结束", demo.LOG_FILE.read_text(encoding="utf-8"))


class TestSnapshot(unittest.TestCase):
    def test_snapshot_canvas_dimensions(self):
        pet = demo.engine.new_pet(now=1.0)
        pixels = demo.snapshot_pixels(pet)
        self.assertEqual(len(pixels), demo._H)
        self.assertTrue(all(len(row) == demo._W for row in pixels))
        self.assertTrue(all(len(px) == 3 for row in pixels for px in row))

    def test_write_bmp_header_and_size(self):
        pixels = [[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                  [(1, 2, 3), (4, 5, 6), (7, 8, 9)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = demo.write_bmp(Path(tmp) / "tiny.bmp", pixels)
            data = path.read_bytes()
        self.assertEqual(data[:2], b"BM")
        self.assertEqual(struct.unpack("<I", data[2:6])[0], len(data))
        width, height = struct.unpack("<ii", data[18:26])
        self.assertEqual((width, height), (3, 2))


if __name__ == "__main__":
    unittest.main()
