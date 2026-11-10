"""手写 24bpp BMP：零依赖把帧缓冲变成 Windows 照片查看器能直接打开的图片。

BMP 结构（本项目只写最朴素的一种）：

* 14 字节文件头：``BM`` 魔数、文件总大小、像素数据偏移 54；
* 40 字节信息头：宽、高、1 面、24 位、无压缩、行跨度、打印分辨率；
* 像素区：**自底向上**逐行存放，每行 BGR 排列、补齐到 4 字节边界。

颜色链路：帧缓冲存的是线性光量，人眼/屏幕走 sRGB 曲线，
所以写出前逐通道做 gamma 校正（sRGB 编码）再裁剪到 0..255——
不做这一步，画面会显得又暗又脏。
"""

from __future__ import annotations

import os
import struct
from typing import List, Sequence

__all__ = ["clamp01", "srgb_encode", "to_byte", "write_bmp"]

_FILE_HEADER_SIZE = 14
_INFO_HEADER_SIZE = 40
_OFFSET = _FILE_HEADER_SIZE + _INFO_HEADER_SIZE  # 54


def clamp01(v: float) -> float:
    """把数值裁进 [0, 1]：过曝的白截到 1，负数的黑截到 0。"""
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def srgb_encode(v: float) -> float:
    """线性值 → sRGB（近似 gamma 2.2 的人眼/显示器响应曲线）。"""
    v = clamp01(v)
    if v <= 0.0031308:
        return 12.92 * v
    return 1.055 * (v ** (1.0 / 2.4)) - 0.055


def to_byte(v: float) -> int:
    """线性浮点 → 0..255 字节：gamma 校正 + 裁剪 + 量化。"""
    return min(255, max(0, int(round(srgb_encode(v) * 255.0))))


def write_bmp(path: str, width: int, height: int, pixels: Sequence[float]) -> None:
    """把线性 RGB 浮点帧缓冲写成 24bpp BMP。

    ``pixels`` 是行主序（从上到下）、长度 ``width * height * 3`` 的序列。
    """
    if width <= 0 or height <= 0:
        raise ValueError("width/height 必须是正数")
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"像素数量应为 {expected}，实际 {len(pixels)}")

    stride = (width * 3 + 3) & ~3  # 每行补齐到 4 字节
    image_size = stride * height
    file_size = _OFFSET + image_size

    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, _OFFSET)
    info_header = struct.pack(
        "<IiiHHIIiiII",
        _INFO_HEADER_SIZE, width, height,
        1, 24,              # 面数、每像素位数
        0, image_size,      # 无压缩、像素区大小
        2835, 2835,         # 72 DPI ≈ 2835 米
        0, 0,               # 调色板
    )

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "wb") as f:
        f.write(file_header)
        f.write(info_header)
        for row in range(height - 1, -1, -1):  # BMP 自底向上：最后一行先写
            base = row * width * 3
            line = bytearray(stride)
            j = 0
            for x in range(width):
                i = base + 3 * x
                line[j] = to_byte(pixels[i + 2])  # B
                line[j + 1] = to_byte(pixels[i + 1])  # G
                line[j + 2] = to_byte(pixels[i])  # R
                j += 3
            f.write(line)  # bytearray(stride) 尾部自带补齐的 0 字节
