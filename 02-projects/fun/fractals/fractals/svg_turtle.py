"""线段集合 → SVG。

SVG 是矢量格式：每条线段一条 ``<line>``，坐标直接来自 turtle 输出，
再经等比映射到画布坐标系（y 轴翻转——数学坐标系 y 向上，SVG y 向下）。
矢量的好处是无限放大不糊：分形「无限细节」的天然载体。
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .turtle import Segment, bounding_box, normalize

__all__ = ["segments_to_svg", "write_svg"]

_SVG_NS = "http://www.w3.org/2000/svg"


def segments_to_svg(
    segments: list[Segment],
    *,
    width: int = 800,
    height: int = 800,
    margin: float = 0.06,
    stroke: str = "#1b5e20",
    stroke_width: float = 1.6,
    background: str = "#fffdf7",
) -> str:
    """把线段集合渲染成完整 SVG 文档字符串。

    线段先归一化到 [0, 1]，再映射进画布；空集合也返回合法空文档。
    """
    if width < 1 or height < 1:
        raise ValueError("width/height 至少为 1")
    if stroke_width <= 0:
        raise ValueError("stroke_width 必须为正")

    normalized = normalize(segments, width=1.0, height=1.0, margin=0.0)
    # 画布内边距（像素）
    pad_x = width * margin
    pad_y = height * margin
    inner_w = width * (1.0 - 2 * margin)
    inner_h = height * (1.0 - 2 * margin)

    lines: list[str] = []
    for s in normalized:
        # 归一化坐标 → 画布像素坐标，y 翻转
        x1 = pad_x + s.x1 * inner_w
        y1 = pad_y + (1.0 - s.y1) * inner_h
        x2 = pad_x + s.x2 * inner_w
        y2 = pad_y + (1.0 - s.y2) * inner_h
        lines.append(
            f'  <line x1="{x1:.2f}" y1="{y1:.2f}" '
            f'x2="{x2:.2f}" y2="{y2:.2f}" />'
        )

    body = "\n".join(lines)
    return (
        f'<svg xmlns="{_SVG_NS}" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <rect width="{width}" height="{height}" fill="{background}" />\n'
        f'  <g stroke="{stroke}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round">\n'
        f"{body}\n"
        f"  </g>\n"
        f"</svg>\n"
    )


def write_svg(path: str, segments: list[Segment], **kwargs) -> None:
    """渲染并写盘；kwargs 透传给 segments_to_svg。"""
    svg = segments_to_svg(segments, **kwargs)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)


def svg_line_count(svg_text: str) -> int:
    """解析 SVG 文档并统计 <line> 元素个数（供测试 / 自检用）。"""
    root = ET.fromstring(svg_text)
    return len(root.findall(f".//{{{_SVG_NS}}}line"))


__all__.append("svg_line_count")
