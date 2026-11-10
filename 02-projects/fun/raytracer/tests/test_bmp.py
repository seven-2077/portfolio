"""bmp 模块测试：文件头结构、行补齐、BGR/自底向上顺序、gamma 与裁剪。"""

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raytracer.bmp import clamp01, srgb_encode, to_byte, write_bmp


def write_tmp(pixels, width, height):
    """写到临时目录，返回 (文件路径, 完整字节)。"""
    tmp = tempfile.mkdtemp(prefix="raytracer_test_")
    path = os.path.join(tmp, "t.bmp")
    write_bmp(path, width, height, pixels)
    with open(path, "rb") as f:
        data = f.read()
    return path, data


class TestHeaderStructure(unittest.TestCase):
    def test_magic_offset_and_header_sizes(self):
        _, data = write_tmp([1.0, 1.0, 1.0], 1, 1)
        self.assertEqual(data[0:2], b"BM")                       # 魔数
        file_size, = struct.unpack_from("<I", data, 2)
        offset, = struct.unpack_from("<I", data, 10)
        info_size, = struct.unpack_from("<I", data, 14)
        self.assertEqual(offset, 54)                             # 14 + 40
        self.assertEqual(info_size, 40)
        self.assertEqual(file_size, len(data))                   # 文件头申报的大小属实

    def test_width_height_bpp_readback(self):
        pixels = [0.2] * (5 * 3 * 3)
        path, data = write_tmp(pixels, 5, 3)
        width, height = struct.unpack_from("<ii", data, 18)
        planes, bpp = struct.unpack_from("<HH", data, 26)
        compression, = struct.unpack_from("<I", data, 30)
        self.assertEqual((width, height), (5, 3))
        self.assertEqual(planes, 1)
        self.assertEqual(bpp, 24)
        self.assertEqual(compression, 0)                         # 无压缩

    def test_image_size_field_matches_padded_stride(self):
        # 宽 3 → 每行 9 字节，补齐到 12；高 2 → 像素区 24 字节
        pixels = [0.0] * (3 * 2 * 3)
        _, data = write_tmp(pixels, 3, 2)
        image_size, = struct.unpack_from("<I", data, 34)
        self.assertEqual(image_size, 12 * 2)
        self.assertEqual(len(data), 54 + image_size)

    def test_pixel_size_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_bmp(os.path.join(tmp, "bad.bmp"), 4, 4, [0.0] * 10)
            with self.assertRaises(ValueError):
                write_bmp(os.path.join(tmp, "bad2.bmp"), 0, 4, [])


class TestPixelLayout(unittest.TestCase):
    def test_bottom_up_bgr_with_padding(self):
        # 1×2：上红下蓝。BMP 自底向上 ⇒ 先写蓝色行，行内 BGR，尾部补 0
        red = [1.0, 0.0, 0.0]
        blue = [0.0, 0.0, 1.0]
        _, data = write_tmp(red + blue, 1, 2)
        first_row = data[54:58]    # 底行（蓝色）：B=255, G=0, R=0, 补 0
        second_row = data[58:62]   # 顶行（红色）：B=0, G=0, R=255, 补 0
        self.assertEqual(first_row, bytes([255, 0, 0, 0]))
        self.assertEqual(second_row, bytes([0, 0, 255, 0]))

    def test_white_black_and_midtone_pixels(self):
        white = [1.0, 1.0, 1.0]
        black = [0.0, 0.0, 0.0]
        mid = [0.5, 0.5, 0.5]
        _, data_w = write_tmp(white, 1, 1)
        self.assertEqual(data_w[54:57], bytes([255, 255, 255]))
        _, data_b = write_tmp(black, 1, 1)
        self.assertEqual(data_b[54:57], bytes([0, 0, 0]))
        _, data_m = write_tmp(mid, 1, 1)
        # sRGB(0.5) ≈ 0.7354 → 0.7354 × 255 ≈ 187.5 → 188（gamma 校正抬亮中间调）
        self.assertEqual(data_m[54:57], bytes([188, 188, 188]))

    def test_out_of_range_values_are_clamped(self):
        crazy = [3.0, -0.5, 1.5]
        _, data = write_tmp(crazy, 1, 1)
        b, g, r = data[54:57]
        self.assertEqual((b, g, r), (255, 0, 255))  # 3.0→255, -0.5→0, 1.5→255


class TestGamma(unittest.TestCase):
    def test_clamp01(self):
        self.assertEqual(clamp01(-1.0), 0.0)
        self.assertEqual(clamp01(2.0), 1.0)
        self.assertEqual(clamp01(0.42), 0.42)

    def test_srgb_endpoints_and_midpoint(self):
        self.assertAlmostEqual(srgb_encode(0.0), 0.0, places=12)
        self.assertAlmostEqual(srgb_encode(1.0), 1.0, places=12)
        self.assertAlmostEqual(srgb_encode(0.5), 0.7354, places=4)

    def test_srgb_is_monotonic(self):
        values = [i / 32 for i in range(33)]
        encoded = [srgb_encode(v) for v in values]
        for a, b in zip(encoded, encoded[1:]):
            self.assertLessEqual(a, b)

    def test_to_byte_roundtrip_bounds(self):
        self.assertEqual(to_byte(-5.0), 0)
        self.assertEqual(to_byte(5.0), 255)
        self.assertEqual(to_byte(0.0), 0)
        self.assertEqual(to_byte(1.0), 255)


if __name__ == "__main__":
    unittest.main()
