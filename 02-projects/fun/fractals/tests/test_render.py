"""渲染层测试：强度映射、字符画、调色板、BMP 读回验证。"""
import os
import struct
import tempfile
import unittest

from fractals.render import (
    GRADIENT,
    ascii_art,
    field_to_pixels,
    gray,
    intensity,
    ocean,
    write_bmp,
)


class TestIntensity(unittest.TestCase):
    def test_none_maps_to_black(self):
        self.assertEqual(intensity(None, 100), 0.0)

    def test_monotone_non_decreasing(self):
        values = [0.0, 1.0, 5.0, 20.0, 99.0, 100.0]
        mapped = [intensity(v, 100) for v in values]
        for a, b in zip(mapped, mapped[1:]):
            self.assertLessEqual(a, b)

    def test_bounded_to_unit_interval(self):
        self.assertEqual(intensity(0.0, 10), 0.0)
        self.assertEqual(intensity(100.0, 10), 1.0)   # 超 max_iter 截断
        self.assertEqual(intensity(-5.0, 10), 0.0)    # 负值防御

    def test_invalid_max_iter_raises(self):
        with self.assertRaises(ValueError):
            intensity(1.0, 0)


class TestAsciiArt(unittest.TestCase):
    FIELD = [[None, 0.0], [10.0, 100.0]]

    def test_dimensions(self):
        art = ascii_art(self.FIELD, 100)
        lines = art.split("\n")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(len(line), 2)

    def test_chars_within_gradient(self):
        art = ascii_art(self.FIELD, 100)
        for ch in art.replace("\n", ""):
            self.assertIn(ch, GRADIENT)

    def test_invert_changes_rendering(self):
        normal = ascii_art(self.FIELD, 100)
        inverted = ascii_art(self.FIELD, 100, invert=True)
        self.assertNotEqual(normal, inverted)

    def test_empty_gradient_raises(self):
        with self.assertRaises(ValueError):
            ascii_art(self.FIELD, 100, gradient="")


class TestPalettes(unittest.TestCase):
    def test_gray_endpoints(self):
        self.assertEqual(gray(0.0), (0, 0, 0))
        self.assertEqual(gray(1.0), (255, 255, 255))
        self.assertEqual(gray(0.5), (128, 128, 128))

    def test_ocean_endpoints_and_range(self):
        self.assertEqual(ocean(0.0), (0, 0, 0))
        self.assertEqual(ocean(1.0), (255, 255, 255))
        for i in range(101):
            r, g, b = ocean(i / 100)
            for v in (r, g, b):
                self.assertTrue(0 <= v <= 255)

    def test_field_to_pixels_dimensions(self):
        pixels = field_to_pixels([[None, 1.0], [2.0, None]], 10)
        self.assertEqual(len(pixels), 2)
        self.assertEqual(len(pixels[0]), 2)
        self.assertEqual(pixels[0][0], (0, 0, 0))   # 集合内 → 纯黑


class TestBmpRoundtrip(unittest.TestCase):
    WIDTH, HEIGHT = 3, 2
    PIXELS = [
        [(255, 0, 0), (0, 255, 0), (0, 0, 255)],   # 顶部行
        [(1, 2, 3), (4, 5, 6), (7, 8, 9)],         # 底部行
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "roundtrip.bmp")
        write_bmp(self.path, self.WIDTH, self.HEIGHT, self.PIXELS)

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self) -> bytes:
        with open(self.path, "rb") as fh:
            return fh.read()

    def test_file_header(self):
        data = self._read()
        self.assertEqual(data[:2], b"BM")
        file_size, = struct.unpack_from("<I", data, 2)
        _res1, _res2, offset = struct.unpack_from("<HHI", data, 6)
        self.assertEqual(_res1, 0)
        self.assertEqual(_res2, 0)
        self.assertEqual(offset, 54)                      # 14 + 40
        stride = (self.WIDTH * 3 + 3) & ~3
        self.assertEqual(file_size, 54 + stride * self.HEIGHT)
        self.assertEqual(file_size, len(data))

    def test_info_header(self):
        data = self._read()
        (hdr_size, width, height, planes, bpp, compression) = \
            struct.unpack_from("<IiiHHI", data, 14)
        self.assertEqual(hdr_size, 40)
        self.assertEqual(width, self.WIDTH)
        self.assertEqual(height, self.HEIGHT)             # 正值 = 自下而上
        self.assertEqual(planes, 1)
        self.assertEqual(bpp, 24)
        self.assertEqual(compression, 0)                  # BI_RGB

    def test_pixel_data_roundtrip(self):
        """BGR + 4 字节对齐 + 倒序存储：读回后逐像素与原图一致。"""
        data = self._read()
        stride = (self.WIDTH * 3 + 3) & ~3
        decoded: list = [None] * self.HEIGHT
        for i in range(self.HEIGHT):            # 文件里第 i 行 = 图像倒数第 i 行
            base = 54 + i * stride
            line = []
            for col in range(self.WIDTH):
                b, g, r = data[base + col * 3: base + col * 3 + 3]
                line.append((r, g, b))
            # 行尾填充必须为 0
            pad = data[base + self.WIDTH * 3: base + stride]
            self.assertEqual(pad, b"\x00" * (stride - self.WIDTH * 3))
            decoded[self.HEIGHT - 1 - i] = line
        self.assertEqual(decoded, self.PIXELS)

    def test_dimension_mismatch_raises(self):
        with self.assertRaises(ValueError):
            write_bmp(os.path.join(self.tmp.name, "bad.bmp"),
                      self.WIDTH, self.HEIGHT, self.PIXELS[:1])
        with self.assertRaises(ValueError):
            write_bmp(os.path.join(self.tmp.name, "bad2.bmp"),
                      0, self.HEIGHT, self.PIXELS)


if __name__ == "__main__":
    unittest.main()
