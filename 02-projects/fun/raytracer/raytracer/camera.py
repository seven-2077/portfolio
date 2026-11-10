"""针孔相机：把像素网格映射成一束束从镜头出发的视线。

针孔模型没有任何透镜：所有光线都汇聚到 ``origin`` 一个点上，
因此天然全景深（不存在「失焦」）。视场角 ``vfov`` 控制看得多广，
每像素多采样则是在一个像素格子里随机抖动位置，平均掉锯齿。
"""

from __future__ import annotations

import math
import random

from .vec import Ray, Vec3

__all__ = ["Camera"]


class Camera:
    """针孔相机。构造时按 look_from/look_at/vup 搭出相机坐标系。"""

    __slots__ = ("origin", "lower_left", "horizontal", "vertical", "vfov", "aspect")

    def __init__(self, look_from: Vec3, look_at: Vec3, vup: Vec3, vfov_deg: float, aspect: float) -> None:
        self.vfov = math.radians(vfov_deg)
        self.aspect = float(aspect)
        half_h = math.tan(self.vfov * 0.5)
        viewport_height = 2.0 * half_h
        viewport_width = self.aspect * viewport_height

        w = (look_from - look_at).normalized()  # 相机看向 -w 方向
        u = vup.cross(w).normalized()           # 右
        v = w.cross(u)                          # 上

        self.origin = look_from
        self.horizontal = u * viewport_width
        self.vertical = v * viewport_height
        self.lower_left = look_from - self.horizontal * 0.5 - self.vertical * 0.5 - w

    def get_ray(self, s: float, t: float) -> Ray:
        """(s, t) ∈ [0,1]² 是视口上的归一化坐标，(0,0) 是左下角。"""
        direction = self.lower_left + self.horizontal * s + self.vertical * t - self.origin
        return Ray(self.origin, direction.normalized())

    @staticmethod
    def pixel_uv(x: int, y: int, width: int, height: int, rng: random.Random):
        """像素 (x, y) 内的抖动坐标：u 向右，v 向上（图像 y=0 是最上面一行）。"""
        u = (x + rng.random()) / width
        v = 1.0 - (y + rng.random()) / height
        return u, v

    def ray_for_pixel(self, x: int, y: int, width: int, height: int, rng: random.Random) -> Ray:
        """一个采样点对应的视线：像素内随机抖动 → 抗锯齿。"""
        u, v = self.pixel_uv(x, y, width, height, rng)
        return self.get_ray(u, v)
