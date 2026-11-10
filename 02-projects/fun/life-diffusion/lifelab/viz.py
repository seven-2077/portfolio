"""可视化：终端字符动画 + SVG 快照输出（零依赖，纯字符串拼接）。

终端侧：生命游戏字符画 + 固定帧数演示（ANSI 清屏重绘）。
SVG 侧：生命游戏关键时刻快照胶片（单帧传 ``[frame]`` 即可）、
反应扩散浓度场热力转灰度或双色马赛克（按行游程合并，省体积）。
"""

from __future__ import annotations

import sys
import time
from typing import Sequence, TextIO

from .game_of_life import GameOfLife

ANSI_CLEAR = "\x1b[2J\x1b[H"

GRAY_RAMP = tuple("#%02x%02x%02x" % (i, i, i) for i in range(256))
DUO_LOW = "#101826"  # 双色马赛克：低浓度深蓝
DUO_HIGH = "#ffcf56"  # 高浓度暖黄


# ------------------------------------------------------------------ 终端
def render_life_text(
    cells,
    width: int,
    height: int,
    *,
    live_char: str = "\u2588\u2588",
    dead_char: str = "  ",
) -> str:
    """活细胞集合 → 固定尺寸字符画（终端单元格约 2:1，故用双宽字符）。"""
    live = set(cells)
    lines = []
    for y in range(height):
        lines.append("".join(live_char if (x, y) in live else dead_char for x in range(width)))
    return "\n".join(lines)


def animate(
    life: GameOfLife,
    *,
    steps: int,
    delay: float = 0.1,
    out: TextIO | None = None,
    clear: bool = True,
    live_char: str = "\u2588\u2588",
    dead_char: str = "  ",
) -> int:
    """固定帧数演示：先渲染当前帧，每演化一代渲染一帧（共 steps+1 帧）。

    会原地演化传入的 ``life``；返回实际渲染帧数。
    """
    if steps < 0:
        raise ValueError("步数不能为负")
    stream = out if out is not None else sys.stdout
    frames = 0

    def show() -> None:
        nonlocal frames
        header = f"gen {life.generation}   population = {life.population}"
        body = render_life_text(
            life.live_cells, life.width, life.height, live_char=live_char, dead_char=dead_char
        )
        if clear:
            stream.write(ANSI_CLEAR)
        stream.write(f"{header}\n{body}\n")
        stream.flush()
        frames += 1

    for _ in range(steps):
        show()
        if delay > 0:
            time.sleep(delay)
        life.step()
    show()
    return frames


# ------------------------------------------------------------------ SVG 基础
def _esc(text: str) -> str:
    text = str(text)
    for a, b in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;")):
        text = text.replace(a, b)
    return text


def _hex_rgb(color: str) -> tuple[int, int, int]:
    s = color.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"颜色须为 #RRGGBB，收到 {color!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _duo_ramp(low: str, high: str) -> tuple[str, ...]:
    c0, c1 = _hex_rgb(low), _hex_rgb(high)
    return tuple(
        "#%02x%02x%02x" % tuple(round(a + (b - a) * i / 255) for a, b in zip(c0, c1))
        for i in range(256)
    )


def _levels(field, vmin: float | None, vmax: float | None) -> list[int]:
    vals = [float(x) for x in field]
    if not vals:
        raise ValueError("浓度场为空")
    lo = min(vals) if vmin is None else float(vmin)
    hi = max(vals) if vmax is None else float(vmax)
    span = (hi - lo) or 1.0
    return [int(min(1.0, max(0.0, (x - lo) / span)) * 255 + 0.5) for x in vals]


def _ramp_for(mode: str, low: str, high: str) -> Sequence[str]:
    if mode == "gray":
        return GRAY_RAMP
    if mode == "duo":
        return _duo_ramp(low, high)
    raise ValueError(f"mode 只能是 'gray' 或 'duo'，收到 {mode!r}")


def _mosaic_rects(
    levels: list[int],
    width: int,
    height: int,
    scale: int,
    ox: int,
    oy: int,
    ramp: Sequence[str],
) -> list[str]:
    """逐行游程合并：同一颜色的连续格子并成一个 rect。"""
    rects = []
    for y in range(height):
        base = y * width
        x = 0
        while x < width:
            lv = levels[base + x]
            x2 = x + 1
            while x2 < width and levels[base + x2] == lv:
                x2 += 1
            rects.append(
                f'<rect x="{ox + x * scale}" y="{oy + y * scale}" '
                f'width="{(x2 - x) * scale}" height="{scale}" fill="{ramp[lv]}"/>'
            )
            x = x2
    return rects


def _svg_open(width: int, height: int) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">')


def life_strip_svg(
    frames: Sequence[GameOfLife],
    *,
    cell: int = 8,
    gap: int = 12,
    live: str = "#111827",
    dead: str = "#ffffff",
    grid: str = "#e5e7eb",
    labels: Sequence[str] | None = None,
    title: str | None = None,
) -> str:
    """关键时刻横向胶片：多帧并排 + 帧题注。"""
    if not frames:
        raise ValueError("帧序列为空")
    fw = frames[0].width * cell
    fh = frames[0].height * cell
    label_h = 16
    title_h = 20 if title else 0
    W = len(frames) * fw + (len(frames) + 1) * gap
    H = fh + label_h + title_h + gap
    parts = [_svg_open(W, H)]
    parts.append(f'<rect width="{W}" height="{H}" fill="#f8fafc"/>')
    for idx, fr in enumerate(frames):
        ox = gap + idx * (fw + gap)
        oy = title_h
        parts.append(f'<rect x="{ox}" y="{oy}" width="{fw}" height="{fh}" fill="{dead}"/>')
        for x, y in sorted(fr.live_cells):
            parts.append(f'<rect x="{ox + x * cell}" y="{oy + y * cell}" '
                         f'width="{cell}" height="{cell}" fill="{live}"/>')
        seg = [f"M{ox + gx * cell} {oy}V{oy + fh}" for gx in range(fr.width + 1)]
        seg += [f"M{ox} {oy + gy * cell}H{ox + fw}" for gy in range(fr.height + 1)]
        parts.append(f'<path d="{" ".join(seg)}" stroke="{grid}" stroke-width="1" fill="none"/>')
        text = labels[idx] if labels and idx < len(labels) else f"gen {idx}"
        parts.append(f'<text x="{ox + fw / 2}" y="{oy + fh + 13}" text-anchor="middle" '
                     f'font-family="monospace" font-size="12" fill="#334155">{_esc(text)}</text>')
    if title:
        parts.append(f'<text x="{gap}" y="14" font-family="monospace" font-size="13" '
                     f'fill="#0f172a">{_esc(title)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def field_snapshot_svg(
    field,
    width: int,
    height: int,
    *,
    scale: int = 4,
    mode: str = "gray",
    low: str = DUO_LOW,
    high: str = DUO_HIGH,
    vmin: float | None = None,
    vmax: float | None = None,
    label: str | None = None,
    background: str = "#ffffff",
) -> str:
    """浓度场 → 热力马赛克 SVG：``mode='gray'`` 灰度，``mode='duo'`` 双色。"""
    if len(field) != width * height:
        raise ValueError(f"场长度 {len(field)} 与 {width}x{height} 不符")
    ramp = _ramp_for(mode, low, high)
    levels = _levels(field, vmin, vmax)
    W, H = width * scale, height * scale
    body_h = H + (18 if label else 0)
    parts = [_svg_open(W, body_h)]
    parts.append(f'<rect width="{W}" height="{body_h}" fill="{background}"/>')
    parts.extend(_mosaic_rects(levels, width, height, scale, 0, 0, ramp))
    if label:
        parts.append(f'<text x="2" y="{H + 14}" font-family="monospace" font-size="13" '
                     f'fill="#0f172a">{_esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def field_atlas_svg(
    panels: Sequence[tuple[object, int, int, str]],
    *,
    columns: int = 3,
    scale: int = 3,
    mode: str = "gray",
    low: str = DUO_LOW,
    high: str = DUO_HIGH,
    vmin: float | None = None,
    vmax: float | None = None,
    gap: int = 14,
    background: str = "#f8fafc",
) -> str:
    """图案图集：多块浓度场按行排列，每块带题注（行主序填充）。"""
    if not panels:
        raise ValueError("图集面板为空")
    if columns < 1:
        raise ValueError("columns 至少为 1")
    ramp = _ramp_for(mode, low, high)
    w, h = int(panels[0][1]), int(panels[0][2])
    if any(int(p[1]) != w or int(p[2]) != h for p in panels):
        raise ValueError("图集各面板尺寸必须一致")
    cols = min(columns, len(panels))
    rows = (len(panels) + cols - 1) // cols
    pw, ph = w * scale, h * scale + 18
    W = cols * pw + (cols + 1) * gap
    H = rows * ph + (rows + 1) * gap
    parts = [_svg_open(W, H)]
    parts.append(f'<rect width="{W}" height="{H}" fill="{background}"/>')
    for idx, (field, _, _, label) in enumerate(panels):
        r, c = divmod(idx, cols)
        ox = gap + c * (pw + gap)
        oy = gap + r * (ph + gap)
        levels = _levels(field, vmin, vmax)
        parts.extend(_mosaic_rects(levels, w, h, scale, ox, oy, ramp))
        parts.append(f'<text x="{ox}" y="{oy + h * scale + 14}" font-family="monospace" '
                     f'font-size="13" fill="#0f172a">{_esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)
