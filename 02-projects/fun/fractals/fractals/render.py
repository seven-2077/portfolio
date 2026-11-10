"""渲染层：字符终端渐变渲染 + 手写 24bpp BMP writer。

BMP 是 Windows 位图的「祖传格式」：14 字节文件头 + 40 字节信息头 +
按 4 字节对齐、自下而上存储的 BGR 像素行。整个 writer 只用 struct 与
bytes 拼接，零第三方依赖——这正是「手写」的意义：格式本身不过 50 行，
看懂它就看懂了所有无压缩位图。
"""
from __future__ import annotations

import math
import struct
from collections.abc import Callable, Sequence

__all__ = [
    "GRADIENT",
    "intensity",
    "ascii_art",
    "gray",
    "ocean",
    "write_bmp",
    "field_to_pixels",
]

# 亮度字符渐变表：暗 → 亮（空格最暗，@ 最亮）
GRADIENT = " .:-=+*#%@"

RGB = tuple[int, int, int]
Field = Sequence[Sequence[float | None]]


# ----------------------------------------------------------------------
# 数值 → 强度
# ----------------------------------------------------------------------

def intensity(value: float | None, max_iter: int, *, gamma: float = 0.6) -> float:
    """把平滑迭代数映射到 [0, 1]。

    集合内（None）为 0（纯黑），集合外用 log 压缩——否则靠近边界的
    高迭代区会集体冲到 1，细节全糊成一片白。
    """
    if value is None:
        return 0.0
    if max_iter < 1:
        raise ValueError("max_iter 至少为 1")
    t = math.log1p(max(value, 0.0)) / math.log1p(float(max_iter))
    t = min(max(t, 0.0), 1.0)
    return t ** gamma


# ----------------------------------------------------------------------
# 字符终端渲染
# ----------------------------------------------------------------------

def ascii_art(
    field: Field,
    max_iter: int,
    *,
    gradient: str = GRADIENT,
    gamma: float = 0.6,
    invert: bool = False,
) -> str:
    """把场渲染成等宽字符画；每行一个字符串，行数 = 场高，列数 = 场宽。

    ``invert=True`` 时反转亮度（集合内变最亮字符，适合浅色终端）。
    """
    if not gradient:
        raise ValueError("gradient 不能为空")
    last = len(gradient) - 1
    lines: list[str] = []
    for row in field:
        chars: list[str] = []
        for value in row:
            t = intensity(value, max_iter, gamma=gamma)
            if invert:
                t = 1.0 - t
            chars.append(gradient[min(last, int(round(t * last)))])
        lines.append("".join(chars))
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 调色板：t ∈ [0, 1] → RGB
# ----------------------------------------------------------------------

def gray(t: float) -> RGB:
    """灰度：黑 → 白。"""
    v = min(255, max(0, int(round(t * 255))))
    return (v, v, v)


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


# 深海色带：黑 → 深蓝 → 青 → 黄 → 白
_OCEAN_STOPS: tuple[RGB, ...] = (
    (0, 0, 0),
    (10, 18, 78),
    (24, 110, 180),
    (70, 220, 220),
    (255, 235, 130),
    (255, 255, 255),
)


def ocean(t: float) -> RGB:
    """分段线性「深海」配色：黑 → 深蓝 → 青 → 黄 → 白。"""
    t = min(max(t, 0.0), 1.0)
    pos = t * (len(_OCEAN_STOPS) - 1)
    idx = min(len(_OCEAN_STOPS) - 2, int(pos))
    local = pos - idx
    return _lerp(_OCEAN_STOPS[idx], _OCEAN_STOPS[idx + 1], local)


# ----------------------------------------------------------------------
# 位图像素
# ----------------------------------------------------------------------

def field_to_pixels(
    field: Field,
    max_iter: int,
    *,
    palette: Callable[[float], RGB] = ocean,
    gamma: float = 0.6,
) -> list[list[RGB]]:
    """场 → 逐像素 RGB（行优先，row 0 在顶部）。"""
    return [
        [palette(intensity(value, max_iter, gamma=gamma)) for value in row]
        for row in field
    ]


# ----------------------------------------------------------------------
# 手写 24bpp BMP writer
# ----------------------------------------------------------------------

_BMP_FILE_HEADER_SIZE = 14
_BMP_INFO_HEADER_SIZE = 40


def write_bmp(
    path: str,
    width: int,
    height: int,
    pixels: Sequence[Sequence[RGB]],
) -> None:
    """写 24bpp、自下而上、行按 4 字节对齐的未压缩 BMP。

    ``pixels`` 为 row 0 在顶部的 RGB 元组矩阵；文件内部按 BMP 规范
    从最后一行开始存。Windows 照片查看器 / 画图可直接打开。
    """
    if width < 1 or height < 1:
        raise ValueError("width/height 至少为 1")
    if len(pixels) != height:
        raise ValueError(f"像素行数 {len(pixels)} 与 height {height} 不符")

    row_stride = (width * 3 + 3) & ~3  # 4 字节对齐
    image_size = row_stride * height
    pixel_data_offset = _BMP_FILE_HEADER_SIZE + _BMP_INFO_HEADER_SIZE
    file_size = pixel_data_offset + image_size

    out = bytearray()
    # BITMAPFILEHEADER: 'BM' + 文件大小 + 保留 + 像素数据偏移
    out += b"BM"
    out += struct.pack("<IHHI", file_size, 0, 0, pixel_data_offset)
    # BITMAPINFOHEADER: 40 字节，负 height 表示自上而下——我们按规范用正值 + 倒序
    out += struct.pack(
        "<IiiHHIIiiII",
        _BMP_INFO_HEADER_SIZE,
        width,
        height,
        1,          # planes
        24,         # bpp
        0,          # BI_RGB（未压缩）
        image_size,
        2835,       # 72 DPI ≈ 2835 px/m
        2835,
        0,          # 调色板颜色数
        0,          # 重要颜色数
    )

    pad = b"\x00" * (row_stride - width * 3)
    for row in reversed(pixels):
        if len(row) != width:
            raise ValueError(f"像素列数 {len(row)} 与 width {width} 不符")
        line = bytearray()
        for r, g, b in row:
            line += bytes((b & 0xFF, g & 0xFF, r & 0xFF))  # BMP 存 BGR
        out += bytes(line) + pad

    with open(path, "wb") as fh:
        fh.write(out)
