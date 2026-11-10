"""DDA 射线投射：每屏幕列一条射线，求墙距 → 鱼眼校正 → 明暗 → 纹理列。

核心是 Lodev 经典的 **Amanatides & Woo 网格 DDA**：射线方向取单位向量
``(cosθ, sinθ)``, 每走一步只跳到「下一个网格边界」而不是逐像素采样，
所以撞上墙只需要 `O(墙距)` 次整数步，一列一条射线的成本极低。

距离语义（面试常问，这里写清楚）::

    dist      cast_ray 返回的**欧氏距离**（沿射线真的走了多远）
    perp      dist × cos(射线角 − 朝向角) = **垂直距离**（鱼眼校正后）
              正是因为屏幕边缘的射线斜着走、测出来的距离天然偏长，
              直接拿它画墙会把平面墙画成圆筒 —— 乘上 cos 就把「斜边」
              压回「直角边」，一堵平墙于是保持平直。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

__all__ = ["RayHit", "cast_ray", "fisheye_correct", "shade_char",
           "texture_column", "sample_texel", "render_walls",
           "MATERIALS", "SHADE_RAMP", "MAX_DEPTH"]

SHADE_RAMP = " .:-=+*#%@"          # 亮度 → 字符表（0 最暗 = 空格）
MAX_DEPTH = 26.0                    # 射线步进上限（地图对角线都在这以内）
SIDE_FACTOR = 0.72                  # 侧向墙（N/S 面）比正对的墙暗一档
_FALLOFF_A, _FALLOFF_B, _FLOOR = 1.05, 0.072, 0.06

# 墙材质：字符图案按列采样，数字是「材质自身亮度」0-9，
# 距离明暗再在这张底图上乘系数，最后落到 SHADE_RAMP 上。
MATERIALS: Dict[int, Dict[str, object]] = {
    1: {"name": "brick", "pattern": (
        "99993999", "99993999", "33333333",
        "39999999", "39999999", "33333333")},
    2: {"name": "stone", "pattern": (
        "77677776", "67776776", "77676677", "66766766")},
    3: {"name": "panel", "pattern": (
        "9993", "6663", "9993", "6663", "9993", "3333")},
}


@dataclass
class RayHit:
    """一条射线的结果：``dist`` 是欧氏距离，配合朝向可推出垂直距离。"""

    hit: bool
    dist: float
    side: int          # 0 = 竖直墙面（E/W 面），1 = 水平墙面（N/S 面）
    cell_x: int
    cell_y: int
    material: int
    wall_x: float      # 命中点在墙面方向上的 [0,1) 坐标（纹理横坐标）
    hit_x: float
    hit_y: float


def fisheye_correct(dist: float, angle_delta: float) -> float:
    """把斜着量出来的欧氏距离压回垂直距离（鱼眼校正）。"""
    return dist * math.cos(angle_delta)


def cast_ray(gmap, ox: float, oy: float, angle: float,
             max_depth: float = MAX_DEPTH) -> RayHit:
    """从 (ox, oy) 沿 ``angle`` 走 DDA，直到撞墙或超过 ``max_depth``。"""
    dir_x, dir_y = math.cos(angle), math.sin(angle)
    map_x, map_y = math.floor(ox), math.floor(oy)
    if gmap.is_wall_cell(map_x, map_y):        # 起点陷在墙里（不该发生）
        return RayHit(True, 0.0, 0, map_x, map_y, gmap.cell(map_x, map_y),
                      0.0, ox, oy)
    delta_x = abs(1.0 / dir_x) if dir_x else math.inf
    delta_y = abs(1.0 / dir_y) if dir_y else math.inf
    step_x = 1 if dir_x > 0 else -1
    step_y = 1 if dir_y > 0 else -1
    side_x = ((map_x + 1) - ox) * delta_x if dir_x > 0 else \
             (ox - map_x) * delta_x
    side_y = ((map_y + 1) - oy) * delta_y if dir_y > 0 else \
             (oy - map_y) * delta_y
    side, dist = 0, 0.0
    while dist <= max_depth:
        if side_x < side_y:
            map_x, side, dist = map_x + step_x, 0, side_x
            side_x += delta_x
        else:
            map_y, side, dist = map_y + step_y, 1, side_y
            side_y += delta_y
        if gmap.is_wall_cell(map_x, map_y):
            hit_x = ox + dist * dir_x
            hit_y = oy + dist * dir_y
            wall_x = (hit_y - map_y) if side == 0 else (hit_x - map_x)
            wall_x -= math.floor(wall_x)
            # 让纹理朝向随射线方向翻转，避免墙面左右镜像跳变
            if (side == 0 and dir_x > 0) or (side == 1 and dir_y < 0):
                wall_x = 1.0 - wall_x
            return RayHit(True, dist, side, map_x, map_y,
                          gmap.cell(map_x, map_y), min(wall_x, 0.999999),
                          hit_x, hit_y)
    return RayHit(False, max_depth, side, map_x, map_y, 0, 0.0,
                  ox + max_depth * dir_x, oy + max_depth * dir_y)


# ---------------------------------------------------------------- 纹理与明暗
def _texture(material: int) -> Tuple[str, ...]:
    return MATERIALS.get(material, MATERIALS[1])["pattern"]  # type: ignore[return-value]


def texture_column(material: int, wall_x: float) -> str:
    """按墙面横坐标取纹理的一整列（从上到下），返回亮度数字串。"""
    pattern = _texture(material)
    width, height = len(pattern[0]), len(pattern)
    col = min(int(wall_x % 1.0 * width), width - 1)
    return "".join(pattern[row][col] for row in range(height))


def sample_texel(material: int, wall_x: float, v: float) -> int:
    """取单个纹素：``v ∈ [0,1)`` 是墙面纵坐标，返回 0-9 亮度。"""
    pattern = _texture(material)
    width, height = len(pattern[0]), len(pattern)
    col = min(int(wall_x % 1.0 * width), width - 1)
    row = min(int(v % 1.0 * height), height - 1)
    return int(pattern[row][col])


def shade_char(dist: float, side: int, lum: int) -> str:
    """距离衰减 × 朝向修正 × 材质亮度 → 明暗表里的一个字符。"""
    brightness = max(_FLOOR, _FALLOFF_A - _FALLOFF_B * dist)
    if side == 1:
        brightness *= SIDE_FACTOR
    level = (lum / 9.0) * brightness
    index = round(level * (len(SHADE_RAMP) - 1))
    return SHADE_RAMP[max(0, min(index, len(SHADE_RAMP) - 1))]


# ---------------------------------------------------------------- 整屏墙面
def render_walls(gmap, player, buf, width: int, view_h: int):
    """逐列投射并把墙画进帧缓冲，返回逐列垂直距离的 z-buffer。

    ``buf`` 只要求有 ``put(x, y, ch)`` 方法（鸭子类型，方便测试）。
    """
    zbuf = [MAX_DEPTH] * width
    angle0 = player.angle
    tan_half = math.tan(player.fov * 0.5)
    for x in range(width):
        cam = 2.0 * (x + 0.5) / width - 1.0
        ray_angle = angle0 + math.atan(cam * tan_half)
        hit = cast_ray(gmap, player.x, player.y, ray_angle)
        perp = fisheye_correct(hit.dist, ray_angle - angle0)
        if not hit.hit:
            continue
        zbuf[x] = perp
        line_h = min(view_h / max(perp, 1e-6), view_h * 40)
        start = int(view_h * 0.5 - line_h * 0.5)
        tex_digits = [int(c) for c in texture_column(hit.material, hit.wall_x)]
        t_h = len(tex_digits)
        for y in range(max(0, start), min(view_h, start + int(line_h) + 1)):
            v = (y - start + 0.5) / line_h
            lum = tex_digits[min(int(v * t_h), t_h - 1)]
            buf.put(x, y, shade_char(perp, hit.side, lum))
    return zbuf
