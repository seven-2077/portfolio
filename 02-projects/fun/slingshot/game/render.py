"""渲染：终端实时字符画 + 结果帧 SVG 导出。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from physics.structure import MATERIALS
from game.world import World

PROJ_CHAR = "●"
DEBRIS_CHAR = "·"
GROUND_CHAR = "="


class TerminalRenderer:
    """把世界画进字符网格：固定物理步长驱动，逐帧重绘。"""

    def __init__(self, world: World, cols: int = 80, rows: int = 18):
        self.world = world
        self.cols = cols
        self.rows = rows
        self.view_bottom = world.ground_y + 2.0
        self._vt = False
        self._first = True

    # —— 坐标映射 ——

    def _cell_of(self, x: float, y: float) -> tuple[int, int]:
        c = int(x / self.world.width * self.cols)
        r = int(y / self.view_bottom * self.rows)
        return max(0, min(self.rows - 1, r)), max(0, min(self.cols - 1, c))

    # —— 组帧 ——

    def draw(self, hud: dict | None = None) -> str:
        hud = hud or {}
        w = self.world
        grid = [[" "] * self.cols for _ in range(self.rows)]

        # 地面
        for r in range(self.rows):
            y_mid = (r + 0.5) * self.view_bottom / self.rows
            if y_mid >= w.ground_y:
                for c in range(self.cols):
                    grid[r][c] = GROUND_CHAR

        # 方块
        for b in w.blocks:
            r0, c0 = self._cell_of(b.left, b.top)
            r1, c1 = self._cell_of(b.right - 1e-9, b.bottom - 1e-9)
            ch = b.material.char
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    grid[r][c] = ch

        # 碎块
        for q, _ in w.debris:
            r, c = self._cell_of(q.x, q.y)
            grid[r][c] = DEBRIS_CHAR

        # 弹丸 + 皮筋
        if w.projectile is not None:
            pr, pc = self._cell_of(w.projectile.p.x, w.projectile.p.y)
            if w.holding:
                for tip in w.tips:
                    self._line(grid, tip.x, tip.y, w.projectile.p.x, w.projectile.p.y)
            grid[pr][pc] = PROJ_CHAR

        lines = [self._hud(hud)] + ["".join(row) for row in grid]
        return "\n".join(lines)

    def _line(self, grid: list[list[str]], x0: float, y0: float, x1: float, y1: float) -> None:
        r0, c0 = self._cell_of(x0, y0)
        r1, c1 = self._cell_of(x1, y1)
        n = max(abs(r1 - r0), abs(c1 - c0), 1)
        ch = "\\" if (r1 - r0) * (c1 - c0) >= 0 else "/"
        for i in range(1, n):
            r = round(r0 + (r1 - r0) * i / n)
            c = round(c0 + (c1 - c0) * i / n)
            if 0 <= r < self.rows and 0 <= c < self.cols and grid[r][c] == " ":
                grid[r][c] = ch

    def _hud(self, hud: dict) -> str:
        left = hud.get("ammo_left", 0)
        total = hud.get("ammo_total", 0)
        ammo = "●" * left + "○" * (total - left)
        line1 = (
            f"关卡{hud.get('level', '?')} {hud.get('name', '')} | "
            f"得分 {hud.get('score', 0)} | 弹丸 {ammo} | "
            f"破坏 {hud.get('broken', 0)}/{hud.get('total', 0)} "
            f"({hud.get('rate', 0) * 100:.0f}%)"
        )
        status = hud.get("status", "")
        aim = hud.get("aim")
        aim_txt = f" | 瞄准 {aim[0]:.0f}° {aim[1] * 100:.0f}%" if aim else ""
        return (line1 + "\n" + status + aim_txt)[: self.cols + 40]

    # —— 输出 ——

    def show(self, hud: dict | None = None) -> None:
        """原地重绘（Windows 终端先开 VT 转义）。"""
        if not self._vt:
            os.system("")
            self._vt = True
        frame = self.draw(hud)
        prefix = "\033[2J\033[H" if self._first else "\033[H"
        self._first = False
        sys.stdout.write(prefix + frame + "\033[J")
        sys.stdout.flush()

    @staticmethod
    def finish() -> None:
        """帧循环结束，换行交还提示符。"""
        sys.stdout.write("\033[0m\n")
        sys.stdout.flush()


# —— SVG 导出 ——

SCALE = 22.0


def export_svg(
    world: World,
    path: str | Path,
    *,
    title: str,
    score_line: str = "",
    subtitle: str = "",
) -> Path:
    """把结构最终状态（含碎块）导出为 SVG 矢量图。"""
    w, h = world.width * SCALE, world.height * SCALE

    def X(v: float) -> float:
        return round(v * SCALE, 2)

    def Y(v: float) -> float:
        return round(v * SCALE, 2)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
        f'height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
        f"<title>{escape(title)}</title>",
        f'<rect x="0" y="0" width="{X(w)}" height="{Y(h)}" fill="#eef4fa"/>',
        f'<rect x="0" y="{Y(world.ground_y)}" width="{X(w)}" '
        f'height="{Y(world.height - world.ground_y)}" fill="#d9cfbc"/>',
        f'<line x1="0" y1="{Y(world.ground_y)}" x2="{X(w)}" y2="{Y(world.ground_y)}" '
        f'stroke="#6a9c48" stroke-width="4"/>',
    ]

    # 弹弓架
    ax, ay = world.anchor
    parts.append(
        f'<path d="M {X(ax)} {Y(ay + 4)} L {X(ax)} {Y(ay)} M {X(ax)} {Y(ay)} '
        f'L {X(ax - 0.8)} {Y(ay - 0.15)} M {X(ax)} {Y(ay)} L {X(ax + 0.8)} {Y(ay - 0.15)}" '
        f'stroke="#7c4b28" stroke-width="5" fill="none" stroke-linecap="round"/>'
    )

    # 飞行轨迹
    if len(world.trail) > 1:
        pts = " ".join(f"{X(x)},{Y(y)}" for x, y in world.trail[::4])
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="#e74c3c" stroke-width="2" '
            f'opacity="0.5" stroke-dasharray="7 5"/>'
        )

    # 方块（按耐久剩余给一点透明度反馈）
    for b in world.blocks:
        m = b.material
        frac = max(0.25, b.hp / m.durability)
        parts.append(
            f'<rect x="{X(b.left)}" y="{Y(b.top)}" width="{X(b.w)}" height="{Y(b.h)}" '
            f'fill="{m.color}" fill-opacity="{round(m.opacity * (0.55 + 0.45 * frac), 2)}" '
            f'stroke="#3a3d42" stroke-width="1.6" rx="3"/>'
        )

    # 碎块
    for q, mat in world.debris:
        parts.append(
            f'<circle cx="{X(q.x)}" cy="{Y(q.y)}" r="{X(0.16)}" '
            f'fill="{MATERIALS[mat].color}" stroke="#3a3d42" stroke-width="0.8"/>'
        )

    # 弹丸
    if world.projectile is not None:
        p = world.projectile
        parts.append(
            f'<circle cx="{X(p.p.x)}" cy="{Y(p.p.y)}" r="{X(p.r)}" fill="#e74c3c" '
            f'stroke="#8c2b21" stroke-width="1.5"/>'
        )

    # HUD 文本
    parts.append(
        f'<text x="{X(2)}" y="{Y(3.4)}" font-size="34" font-weight="bold" '
        f'font-family="Consolas, Microsoft YaHei, sans-serif" fill="#262a30">'
        f"{escape(title)}</text>"
    )
    if subtitle:
        parts.append(
            f'<text x="{X(2)}" y="{Y(6.2)}" font-size="22" '
            f'font-family="Consolas, Microsoft YaHei, sans-serif" fill="#5b616b">'
            f"{escape(subtitle)}</text>"
        )
    if score_line:
        parts.append(
            f'<text x="{X(2)}" y="{Y(8.8)}" font-size="24" font-weight="bold" '
            f'font-family="Consolas, Microsoft YaHei, sans-serif" fill="#b0722a">'
            f"{escape(score_line)}</text>"
        )

    # 图例
    lx = world.width - 26.0
    for i, (name, m) in enumerate(MATERIALS.items()):
        y = 3.0 + i * 2.2
        parts.append(
            f'<rect x="{X(lx)}" y="{Y(y)}" width="{X(1.6)}" height="{X(1.6)}" '
            f'fill="{m.color}" stroke="#3a3d42" stroke-width="1.2" rx="2"/>'
        )
        parts.append(
            f'<text x="{X(lx + 2.2)}" y="{Y(y + 1.35)}" font-size="18" '
            f'font-family="Microsoft YaHei, sans-serif" fill="#4a4f57">{name}</text>'
        )
    parts.append("</svg>")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
