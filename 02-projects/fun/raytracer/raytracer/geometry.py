"""几何体与求交：球、无限平面，以及「射线 × 物体集合」的最近命中调度。

求交统一返回「最近的根」``t ∈ [t_min, t_max]`` 与交点法线；
法线永远朝向射线来的一侧（``front_face`` 记录原始朝向），
这样玻璃内部的二次入射也能拿到正确的界面法线。
"""

from __future__ import annotations

import math
from typing import Optional

from .vec import Ray, Vec3

__all__ = ["T_MIN", "HitRecord", "Sphere", "Plane", "HittableList"]

T_MIN = 1e-4  # 避免阴影/反射射线与自身所在表面自交的偏移量


class HitRecord:
    """一次命中：交点、法线、距离 t、正反面、材质。"""

    __slots__ = ("point", "normal", "t", "front_face", "material")

    def __init__(self, point: Vec3, normal: Vec3, t: float, front_face: bool, material) -> None:
        self.point = point
        self.normal = normal  # 已按 front_face 翻转，恒与射线相向
        self.t = t
        self.front_face = front_face
        self.material = material


class Sphere:
    """球体：解 |O + tD - C|² = r² 的一元二次方程。"""

    __slots__ = ("center", "radius", "radius_sq", "material")

    def __init__(self, center: Vec3, radius: float, material) -> None:
        self.center = center
        self.radius = float(radius)
        self.radius_sq = self.radius * self.radius
        self.material = material

    def hit(self, ray: Ray, t_min: float = T_MIN, t_max: float = math.inf) -> Optional[HitRecord]:
        # 热路径上用分量级标量运算解方程，少造中间向量
        center = self.center
        ox = ray.origin.x - center.x
        oy = ray.origin.y - center.y
        oz = ray.origin.z - center.z
        dx, dy, dz = ray.direction.x, ray.direction.y, ray.direction.z
        a = dx * dx + dy * dy + dz * dz
        b = ox * dx + oy * dy + oz * dz  # dot(oc, dir)
        c = ox * ox + oy * oy + oz * oz - self.radius_sq
        disc = b * b - a * c
        if disc < 0.0:
            return None  # 没有实根：射线擦身而过
        sqrt_disc = math.sqrt(disc)
        t = (-b - sqrt_disc) / a  # 先试近根
        if t < t_min or t > t_max:
            t = (-b + sqrt_disc) / a  # 再试远根（例如从球内部出发）
            if t < t_min or t > t_max:
                return None
        point = ray.origin + ray.direction * t
        outward = (point - center) * (1.0 / self.radius)
        front_face = ray.direction.dot(outward) < 0.0
        normal = outward if front_face else -outward
        return HitRecord(point, normal, t, front_face, self.material)


class Plane:
    """无限平面：t = ((P0 - O) · n) / (D · n)，单面法线 + 背面翻转。"""

    __slots__ = ("point", "normal", "material")

    def __init__(self, point: Vec3, normal: Vec3, material) -> None:
        self.point = point
        self.normal = normal.normalized()
        self.material = material

    def hit(self, ray: Ray, t_min: float = T_MIN, t_max: float = math.inf) -> Optional[HitRecord]:
        denom = ray.direction.dot(self.normal)
        if abs(denom) < 1e-9:
            return None  # 与平面平行（含贴着平面滑行）
        t = (self.point - ray.origin).dot(self.normal) / denom
        if t < t_min or t > t_max:
            return None  # 交点在射线背后或超出范围
        point = ray.origin + ray.direction * t
        front_face = denom < 0.0
        normal = self.normal if front_face else -self.normal
        return HitRecord(point, normal, t, front_face, self.material)


class HittableList:
    """物体集合：逐个询问，只保留最近的一次命中（顺手收紧 t 上限做剪枝）。"""

    __slots__ = ("objects",)

    def __init__(self, objects=()) -> None:
        self.objects = list(objects)

    def add(self, obj) -> None:
        self.objects.append(obj)

    def hit(self, ray: Ray, t_min: float = T_MIN, t_max: float = math.inf) -> Optional[HitRecord]:
        closest = t_max
        best: Optional[HitRecord] = None
        for obj in self.objects:
            rec = obj.hit(ray, t_min, closest)
            if rec is not None:
                best = rec
                closest = rec.t
        return best
