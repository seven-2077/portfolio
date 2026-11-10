"""SVG 黄道带星图：圆形天球 + 十二宫 30° 分区刻度与标签 + 太阳/行星标记。

约定
----
- λ = 0°（春分点）画在正右方，黄经逆时针增大（与天球上行星视运动一致）；
- 黄道带为 262–316 半径的圆环，12 宫各占 30°，交替底色、边界刻线；
- 行星按地心黄经落点，引导线连到带内，标记半径按经度排序错开避免重叠；
- 太阳单独落在内圈，圆心是观测者（地球）。
"""

from __future__ import annotations

import html
import math
from pathlib import Path

from .planet import ZODIAC, geocentric_lonlat, sun_lonlat
from .time_utils import jd_to_datetime

__all__ = ["build_chart", "save_chart", "PLANET_STYLE"]

# key -> (中文名, 天文符号, 颜色)
PLANET_STYLE: dict[str, tuple[str, str, str]] = {
    "mercury": ("水星", "\u263f", "#9aa0a6"),   # ☿
    "venus": ("金星", "\u2640", "#f2c14e"),     # ♀
    "mars": ("火星", "\u2642", "#e2574c"),      # ♂
    "jupiter": ("木星", "\u2643", "#e0a35c"),   # ♃
    "saturn": ("土星", "\u2644", "#d9c76b"),    # ♄
    "uranus": ("天王星", "\u2645", "#5fd3c8"),  # ♅
    "neptune": ("海王星", "\u2646", "#6a8cff"),  # ♆
}
SUN_STYLE = ("太阳", "\u2609", "#ffb340")        # ☉

SIZE = 760          # 画布边长
CX, CY = 380.0, 396.0  # 圆心（略微下移给标题留白）
R_OUT = 316.0       # 天球外缘
R_IN = 262.0        # 黄道带内缘
_FONT = "Segoe UI, Microsoft YaHei, sans-serif"

# 行星标记半径（按黄经排序后循环取用，错开相邻行星）
_PLANET_RADII = (234.0, 204.0, 174.0, 144.0)
_SUN_R = 108.0


def _pt(r: float, lon: float) -> tuple[float, float]:
    """黄经 → SVG 坐标（λ=0 在右，逆时针增大；SVG 的 y 轴向下）。"""
    a = math.radians(lon)
    return CX + r * math.cos(a), CY - r * math.sin(a)


def _sector_path(lon0: float, lon1: float) -> str:
    """12 宫扇形环带路径（lon0 → lon1，黄经逆时针）。"""
    x0o, y0o = _pt(R_OUT, lon0)
    x1o, y1o = _pt(R_OUT, lon1)
    x1i, y1i = _pt(R_IN, lon1)
    x0i, y0i = _pt(R_IN, lon0)
    return (
        f"M {x0o:.2f},{y0o:.2f} "
        f"A {R_OUT},{R_OUT} 0 0 0 {x1o:.2f},{y1o:.2f} "
        f"L {x1i:.2f},{y1i:.2f} "
        f"A {R_IN},{R_IN} 0 0 1 {x0i:.2f},{y0i:.2f} Z"
    )


def _text(x: float, y: float, content: str, size: float, fill: str,
          anchor: str = "middle", weight: str = "normal") -> str:
    esc = html.escape(content, quote=True)
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{esc}</text>'
    )


def build_chart(jd: float, title: str | None = None) -> str:
    """生成黄道星图 SVG 字符串。

    title=None → 自动用 JD 对应日期做标题；传字符串自定义标题；
    传 "" → 不显示标题（"可选日期标题"）。
    """
    if title is None:
        headline = f"黄道星图 · {jd_to_datetime(jd):%Y-%m-%d %H:%M} UTC"
    else:
        headline = title

    p: list[str] = []
    p.append('<?xml version="1.0" encoding="UTF-8"?>')
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" '
        f'height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}" '
        f'font-family="{_FONT}">'
    )
    p.append(f'<rect width="{SIZE}" height="{SIZE}" fill="#0b1020"/>')

    # ---- 标题 ----
    if headline:
        p.append(_text(CX, 44, headline, 21, "#e8ecf8", weight="bold"))
    p.append(
        _text(CX, 66, f"JD {jd:.1f} · 地心黄经 · 简化 J2000 历表（约 ±1°）",
              12, "#8fa0c8")
    )

    # ---- 黄道带：12 宫扇形 + 分区线 + 刻度 + 标签 ----
    for k in range(12):
        fill = "#131b33" if k % 2 == 0 else "#0f152a"
        p.append(f'<path d="{_sector_path(k * 30.0, (k + 1) * 30.0)}" '
                 f'fill="{fill}" stroke="none"/>')
    for k in range(12):                       # 30° 分区线
        x0, y0 = _pt(R_IN, k * 30.0)
        x1, y1 = _pt(R_OUT, k * 30.0)
        p.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" '
                 f'y2="{y1:.2f}" stroke="#46598f" stroke-width="1.4"/>')
    for deg in range(0, 360, 10):             # 10° 刻度（带外缘向内）
        if deg % 30 == 0:
            continue
        x0, y0 = _pt(R_OUT, deg)
        x1, y1 = _pt(R_OUT - 9, deg)
        p.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" '
                 f'y2="{y1:.2f}" stroke="#5a6da8" stroke-width="1"/>')
    for k in range(12):                       # 度数标签（带内缘）
        x, y = _pt(248.0, k * 30.0)
        p.append(_text(x, y + 3.5, f"{k * 30}\u00b0", 10, "#7d8cb8"))
    for k, (name, sym) in enumerate(ZODIAC):  # 十二宫标签（带中央）
        x, y = _pt(289.0, k * 30.0 + 15.0)
        p.append(_text(x, y + 5, f"{name} {sym}", 14, "#cdd7f5"))
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_OUT}" fill="none" '
             f'stroke="#46598f" stroke-width="1.6"/>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_IN}" fill="none" '
             f'stroke="#46598f" stroke-width="1.2"/>')

    # ---- 太阳 ----
    sun_lon, _ = sun_lonlat(jd)
    sx, sy = _pt(_SUN_R, sun_lon)
    gx0, gy0 = _pt(30.0, sun_lon)
    p.append(f'<line x1="{gx0:.2f}" y1="{gy0:.2f}" x2="{sx:.2f}" '
             f'y2="{sy:.2f}" stroke="{SUN_STYLE[2]}" stroke-width="1.2" '
             f'opacity="0.55"/>')
    p.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="9" '
             f'fill="{SUN_STYLE[2]}" stroke="#0b1020" stroke-width="1.5"/>')
    lx, ly = _pt(_SUN_R + 22, sun_lon)
    p.append(_text(lx, ly + 4, f"{SUN_STYLE[1]}{SUN_STYLE[0]} "
                               f"{sun_lon:.1f}\u00b0", 13, SUN_STYLE[2]))

    # ---- 行星（按黄经排序 → 错开半径）----
    marks: list[tuple[float, str, str, str]] = []
    for key, (name, sym, color) in PLANET_STYLE.items():
        lon, _ = geocentric_lonlat(key, jd)
        marks.append((lon, name, sym, color))
    marks.sort()
    for idx, (lon, name, sym, color) in enumerate(marks):
        r = _PLANET_RADII[idx % len(_PLANET_RADII)]
        px, py = _pt(r, lon)
        gx, gy = _pt(R_IN - 6, lon)
        p.append(f'<line x1="{gx:.2f}" y1="{gy:.2f}" x2="{px:.2f}" '
                 f'y2="{py:.2f}" stroke="{color}" stroke-width="1.1" '
                 f'opacity="0.5"/>')
        p.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6.5" '
                 f'fill="{color}" stroke="#0b1020" stroke-width="1.5"/>')
        right = math.cos(math.radians(lon)) >= 0
        tx = px + (11 if right else -11)
        p.append(_text(tx, py + 4, f"{sym}{name} {lon:.1f}\u00b0", 12.5,
                       color, anchor="start" if right else "end"))

    # ---- 圆心：观测者 ----
    p.append(f'<circle cx="{CX}" cy="{CY}" r="5" fill="#4da6ff" '
             f'stroke="#0b1020" stroke-width="1.5"/>')
    p.append(_text(CX, CY + 22, "地球 · 观测点", 10.5, "#7fa8e8"))

    # ---- 页脚 ----
    p.append(_text(CX, 744,
                   "开普勒方程牛顿迭代求解 · 数据：JPL SSD 近似历表 "
                   "(Standish & Williams 1992)", 10.5, "#6b7a9e"))
    p.append("</svg>")
    return "\n".join(p)


def save_chart(jd: float, path: str | Path, title: str | None = None) -> Path:
    """生成星图并写入 path（自动建父目录），返回 Path。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_chart(jd, title=title), encoding="utf-8")
    return out
