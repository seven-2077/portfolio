"""三种材质模型：Lambert 漫反射、金属、玻璃。

材质与渲染器的分工（Whitted 风格）：

* ``shade_direct`` —— 不透明漫反射表面直接吃光源：反照率 ×（环境光 + Σ直射×cosθ×阴影）；
* ``scatter`` —— 递归部分：返回 (散射光线, 权重) 列表，由渲染器继续追踪；
  金属给 1 条反射光线，玻璃给「反射 + 折射」2 条（全反射时只剩 1 条）；
* ``uses_direct_light`` / ``casts_shadow`` —— 金属、玻璃不吃直射光，玻璃也不投影。
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

from .vec import Ray, Vec3, as_vec3, random_in_unit_sphere, reflect, refract

if TYPE_CHECKING:
    from .geometry import HitRecord

__all__ = ["Material", "Lambert", "Metal", "Glass", "schlick_reflectance", "fresnel_reflectance"]

ScatterEvent = Tuple[Ray, Vec3]  # (散射出去的光线, 这条光线携带的颜色权重)


class Material:
    """材质基类：默认什么都不做（既不吃直射光，也不散射）。"""

    __slots__ = ()

    uses_direct_light = False  # 是否需要渲染器算直射光 + 阴影射线
    casts_shadow = True        # 是否挡住光源（玻璃为 False，光直接穿过）

    def shade_direct(self, hit: "HitRecord", light: Vec3) -> Vec3:
        """直接光照分量。light 是该点收到的总光（环境光 + 各光源贡献）。"""
        return Vec3(0.0, 0.0, 0.0)

    def scatter(self, ray_in: Ray, hit: "HitRecord", rng: random.Random) -> Tuple[ScatterEvent, ...]:
        """递归散射事件列表；空元组表示这条光线到此为止。"""
        return ()


class Lambert(Material):
    """朗伯漫反射：微面元朝向随机，出射亮度只与 cosθ 有关，与观察角无关。"""

    __slots__ = ("albedo",)

    uses_direct_light = True

    def __init__(self, albedo) -> None:
        self.albedo = as_vec3(albedo)  # 反照率：吸收后重新均匀辐射的比例

    def shade_direct(self, hit: "HitRecord", light: Vec3) -> Vec3:
        return self.albedo * light  # 逐分量：红球吸收绿蓝，只把红色弹回来


class Metal(Material):
    """金属：镜面反射 + 粗糙度抖动。

    roughness = 0 是完美镜子；> 0 时反射方向叠加一个球内随机扰动再归一化，
    相当于把「微面元法线随机倾斜」简化成一个锥形模糊。
    """

    __slots__ = ("albedo", "roughness")

    def __init__(self, albedo, roughness: float = 0.0) -> None:
        self.albedo = as_vec3(albedo)
        self.roughness = min(max(float(roughness), 0.0), 1.0)

    def scatter(self, ray_in: Ray, hit: "HitRecord", rng: random.Random):
        direction = reflect(ray_in.direction, hit.normal)
        if self.roughness > 0.0:
            direction = direction + random_in_unit_sphere(rng) * self.roughness
            len_sq = direction.length_squared()
            if len_sq > 1e-12:
                direction = direction * (1.0 / math.sqrt(len_sq))
        if direction.dot(hit.normal) <= 0.0:
            return ()  # 抖进了表面以下：光被吸收（金属背面是黑的）
        return ((Ray(hit.point, direction), self.albedo),)


class Glass(Material):
    """玻璃（电介质）：斯涅尔折射 + 全内反射 + Fresnel 分光。

    * ``front_face`` 决定 eta：空气→玻璃用 1/ior，玻璃→空气用 ior；
    * 反射/折射按 Fresnel 反射率 F 分光（能量守恒：F + (1-F) = 1）；
    * ``schlick=True`` 用 Schlick 五次多项式近似，``False`` 走精确 Fresnel 公式；
    * 折射光线乘上 ``tint``（每穿越一次界面吸收一点，颜色因此累积）。
    """

    __slots__ = ("ior", "tint", "use_schlick")

    casts_shadow = False  # 玻璃不投影：光直接穿过（无焦散，见 README 局限）

    def __init__(self, ior: float = 1.5, tint=(1.0, 1.0, 1.0), schlick: bool = True) -> None:
        self.ior = float(ior)
        self.tint = as_vec3(tint)
        self.use_schlick = bool(schlick)

    def reflectance(self, cos_i: float, eta: float) -> float:
        if self.use_schlick:
            return schlick_reflectance(cos_i, eta)
        return fresnel_reflectance(cos_i, eta)

    def scatter(self, ray_in: Ray, hit: "HitRecord", rng: random.Random):
        eta = (1.0 / self.ior) if hit.front_face else self.ior
        incident = ray_in.direction
        normal = hit.normal
        transmitted = refract(incident, normal, eta)
        if transmitted is None:  # 全内反射：折射分支死亡，100% 走反射
            return ((Ray(hit.point, reflect(incident, normal)), Vec3(1.0, 1.0, 1.0)),)
        cos_i = -incident.dot(normal)
        f = self.reflectance(cos_i, eta)
        return (
            (Ray(hit.point, reflect(incident, normal)), Vec3(f, f, f)),
            (Ray(hit.point, transmitted), self.tint * (1.0 - f)),
        )


# ---------- Fresnel 反射率 ----------

def schlick_reflectance(cos_i: float, eta: float) -> float:
    """Schlick 近似：F ≈ r0 + (1-r0)(1-cos i)^5，r0 = ((1-η)/(1+η))²。"""
    r0 = (1.0 - eta) / (1.0 + eta)
    r0 *= r0
    m = 1.0 - min(max(cos_i, 0.0), 1.0)
    m2 = m * m
    return r0 + (1.0 - r0) * m2 * m2 * m


def fresnel_reflectance(cos_i: float, eta: float) -> float:
    """非偏振光的精确 Fresnel 反射率（Rs、Rp 两偏振取平均），掠入射趋近 1。"""
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    if sin2_t >= 1.0:
        return 1.0  # 全内反射
    cos_t = math.sqrt(1.0 - sin2_t)
    rs = (eta * cos_i - cos_t) / (eta * cos_i + cos_t)
    rp = (eta * cos_t - cos_i) / (eta * cos_t + cos_i)
    return 0.5 * (rs * rs + rp * rp)
