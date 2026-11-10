"""逃逸时间算法 + 平滑着色：Mandelbrot 集与 Julia 集。

两个集合共享同一个核心迭代 z ← z² + c，区别只在于谁固定、谁游走：

* **Mandelbrot**：z₀ = 0，c 遍历复平面上的每个像素——c 的「出生证明」。
* **Julia**：c 固定为一个常数，z₀ 遍历像素——同一套规则在不同初始值下的「全家福」。

平滑着色（continuous / smooth iteration count）用

    μ = n + 1 − log₂(ln|zₙ|)

替代整数迭代数 n：在平方动力学 z ← z² 上恰好多出的 1 被 log₂ 项抵消，
边界不再是一圈圈色带而是细腻渐变——「无限放大永不完结的细节」在颜色上的
体现。与整数着色的对比实测见 ``smooth_escape`` 的连续性说明。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "Viewport",
    "smooth_escape",
    "escapes",
    "mandelbrot_field",
    "julia_field",
    "DEFAULT_MAX_ITER",
]

DEFAULT_MAX_ITER = 256


@dataclass(frozen=True)
class Viewport:
    """复平面视口：实轴 [x_min, x_max] × 虚轴 [y_min, y_max]。"""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def __post_init__(self) -> None:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("viewport 必须满足 x_min < x_max 且 y_min < y_max")

    @classmethod
    def centered(cls, cx: float, cy: float, half_width: float,
                 half_height: float | None = None) -> "Viewport":
        """以 (cx, cy) 为中心构造视口；half_height 缺省时保持 1:1 复平面比例。"""
        if half_width <= 0:
            raise ValueError("half_width 必须为正")
        hh = half_width if half_height is None else half_height
        if hh <= 0:
            raise ValueError("half_height 必须为正")
        return cls(cx - half_width, cx + half_width, cy - hh, cy + hh)

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def point(self, col: int, row: int, px_width: int, px_height: int) -> complex:
        """像素 (col, row) 对应的复数；row 0 视为图像顶部（虚部最大处）。"""
        if not (0 <= col < px_width and 0 <= row < px_height):
            raise ValueError("像素坐标越界")
        re = self.x_min + (col + 0.5) * self.width / px_width
        im = self.y_max - (row + 0.5) * self.height / px_height
        return complex(re, im)

    def contains(self, z: complex) -> bool:
        return self.x_min <= z.real <= self.x_max and self.y_min <= z.imag <= self.y_max


# ----------------------------------------------------------------------
# 核心：逃逸时间 + 平滑着色
# ----------------------------------------------------------------------

def smooth_escape(
    c: complex,
    *,
    max_iter: int = DEFAULT_MAX_ITER,
    z0: complex = 0j,
    escape_radius: float = 2.0,
) -> float | None:
    """返回平滑迭代数 μ；点在集合内（max_iter 次内未逃逸）返回 None。

    ``escape_radius`` 默认取经典判据 |z| > 2：远场很快逃逸、颜色平稳，
    集合的结构因此从背景中凸显出来。可以调大（如 1e6）换取更精细的
    远场色带，代价是背景出现同心环纹。

    连续性说明：若把「迭代 n 次、末值模 M」与「迭代 n+1 次、末值模 M²」
    两处代入公式，两边恰好相差 1、被 log₂ 项抵消（即 z ← z² 的平方关系
    上 μ 守恒）。实际沿实轴扫描（步长 1e-7）时，逃逸计数跳 1 的边界处 μ
    仍残留约 0.1~0.4 的小台阶（整数着色在同处跳整整 1），视觉上几乎不可见。
    """
    if max_iter < 1:
        raise ValueError("max_iter 至少为 1")
    if escape_radius <= 1.0:
        raise ValueError("escape_radius 必须大于 1（对数项才有定义）")
    z = z0
    for n in range(max_iter):
        z = z * z + c
        modulus = abs(z)
        if modulus > escape_radius:
            # μ = n + 1 − log₂(ln|z|)：跨逃逸面连续
            return n + 1.0 - math.log(math.log(modulus)) / math.log(2.0)
        if math.isinf(modulus) or math.isnan(modulus):
            # 数值发散兜底（理论上 |z| > escape_radius 会先触发）
            return float(max_iter)
    return None


def escapes(c: complex, *, max_iter: int = DEFAULT_MAX_ITER,
            z0: complex = 0j, escape_radius: float = 2.0) -> bool:
    """整数逃逸判定：经典 |z| > 2 判据，只关心「逃不逃」。"""
    z = z0
    for _ in range(max_iter):
        z = z * z + c
        if abs(z) > escape_radius:
            return True
    return False


# ----------------------------------------------------------------------
# 场（field）：逐像素计算
# ----------------------------------------------------------------------

def mandelbrot_field(
    width: int,
    height: int,
    viewport: Viewport | None = None,
    *,
    max_iter: int = DEFAULT_MAX_ITER,
    escape_radius: float = 2.0,
) -> list[list[float | None]]:
    """计算 Mandelbrot 场：返回 height 行 × width 列的平滑迭代数矩阵。"""
    if width < 1 or height < 1:
        raise ValueError("width/height 至少为 1")
    vp = viewport or Viewport.centered(-0.5, 0.0, 2.6)
    rows: list[list[float | None]] = []
    for row in range(height):
        line: list[float | None] = []
        for col in range(width):
            c = vp.point(col, row, width, height)
            line.append(smooth_escape(c, max_iter=max_iter,
                                      escape_radius=escape_radius))
        rows.append(line)
    return rows


def julia_field(
    width: int,
    height: int,
    c: complex,
    viewport: Viewport | None = None,
    *,
    max_iter: int = DEFAULT_MAX_ITER,
    z0: complex = 0j,
    escape_radius: float = 2.0,
) -> list[list[float | None]]:
    """计算 Julia 场：c 固定，z₀ 遍历视口像素。"""
    if width < 1 or height < 1:
        raise ValueError("width/height 至少为 1")
    vp = viewport or Viewport.centered(0.0, 0.0, 2.0)
    rows: list[list[float | None]] = []
    for row in range(height):
        line: list[float | None] = []
        for col in range(width):
            z_start = vp.point(col, row, width, height)
            line.append(smooth_escape(c, max_iter=max_iter, z0=z_start,
                                      escape_radius=escape_radius))
        rows.append(line)
    return rows
