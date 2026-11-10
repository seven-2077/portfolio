"""3D 向量与光线：整个渲染器的数学地基。

约定
----
* 参与光照、折射的方向向量一律归一化为单位向量；
* ``Ray.direction`` 是单位向量，因此 ``P(t) = origin + t * direction``
  里的 ``t`` 就是以原点起算的真实距离，求交方程可以按这个前提简化；
* 颜色也是 ``Vec3``（线性 RGB，0..1），只在写出图片时做 sRGB/gamma 校正。
"""

from __future__ import annotations

import math
import random
from typing import Union

__all__ = [
    "Vec3",
    "Ray",
    "as_vec3",
    "dot",
    "cross",
    "reflect",
    "refract",
    "lerp",
    "random_in_unit_sphere",
]

_Number = Union[int, float]


class Vec3:
    """三维向量。所有运算符都返回新对象，没有原地修改。"""

    __slots__ = ("x", "y", "z")

    def __init__(self, x: _Number = 0.0, y: _Number = 0.0, z: _Number = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    # ---------- 构造与转换 ----------

    @classmethod
    def from_iterable(cls, values) -> "Vec3":
        x, y, z = values
        return cls(x, y, z)

    def to_tuple(self):
        return (self.x, self.y, self.z)

    def copy(self) -> "Vec3":
        return Vec3(self.x, self.y, self.z)

    # ---------- 运算符 ----------

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, k) -> "Vec3":
        # 支持标量乘法与逐分量向量乘法（albedo * light 这类颜色运算）
        if isinstance(k, Vec3):
            return Vec3(self.x * k.x, self.y * k.y, self.z * k.z)
        return Vec3(self.x * k, self.y * k, self.z * k)

    def __rmul__(self, k) -> "Vec3":
        return self.__mul__(k)

    def __truediv__(self, k: _Number) -> "Vec3":
        inv = 1.0 / k
        return Vec3(self.x * inv, self.y * inv, self.z * inv)

    def __neg__(self) -> "Vec3":
        return Vec3(-self.x, -self.y, -self.z)

    def __getitem__(self, index: int) -> float:
        return (self.x, self.y, self.z)[index]

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    def __repr__(self) -> str:
        return f"Vec3({self.x:.6g}, {self.y:.6g}, {self.z:.6g})"

    # ---------- 几何运算 ----------

    def dot(self, other: "Vec3") -> float:
        """点乘：长度投影 / 夹角余弦的分子。"""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        """叉乘：得到同时垂直于两个向量的新方向。"""
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def length(self) -> float:
        return math.sqrt(self.length_squared())

    def normalized(self) -> "Vec3":
        """归一化；零向量原样返回，避免除零。"""
        len_sq = self.length_squared()
        if len_sq <= 0.0:
            return Vec3(0.0, 0.0, 0.0)
        inv = 1.0 / math.sqrt(len_sq)
        return Vec3(self.x * inv, self.y * inv, self.z * inv)

    def near_zero(self, tol: float = 1e-8) -> bool:
        return abs(self.x) < tol and abs(self.y) < tol and abs(self.z) < tol


# ---------- 模块级函数 ----------

def as_vec3(value) -> Vec3:
    """把 (x, y, z) 元组/列表或 Vec3 统一成 Vec3。"""
    if isinstance(value, Vec3):
        return value
    return Vec3.from_iterable(value)


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: Vec3, b: Vec3) -> Vec3:
    return a.cross(b)


def lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    """线性插值：t=0 得 a，t=1 得 b。天空渐变就靠它。"""
    return a * (1.0 - t) + b * t


def reflect(incident: Vec3, normal: Vec3) -> Vec3:
    """镜面反射：v' = v - 2(v·n)n。incident 与 normal 均为单位向量。"""
    return incident - normal * (2.0 * incident.dot(normal))


def refract(incident: Vec3, normal: Vec3, eta: float):
    """斯涅尔（Snell）折射。

    ``incident`` 指向表面，``normal`` 与之相向（点积为负），两者都是单位向量；
    ``eta = n1 / n2`` 是入射介质与折射介质的折射率之比。

    折射角超过临界角、发生**全内反射**时返回 ``None``，调用方只走反射分支。
    """
    cos_i = -incident.dot(normal)
    k = 1.0 - eta * eta * (1.0 - cos_i * cos_i)
    if k < 0.0:
        return None  # 全内反射
    return incident * eta + normal * (eta * cos_i - math.sqrt(k))


def random_in_unit_sphere(rng: random.Random) -> Vec3:
    """单位球内均匀取一点（拒绝采样），给金属的粗糙度抖动用。"""
    while True:
        p = Vec3(rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0))
        if p.length_squared() < 1.0:
            return p


class Ray:
    """射线：P(t) = origin + direction * t，t >= 0。

    ``direction`` 保持单位向量，所以 t 就是真实距离（求交、阴影判定都依赖这点）。
    """

    __slots__ = ("origin", "direction")

    def __init__(self, origin: Vec3, direction: Vec3) -> None:
        self.origin = origin
        self.direction = direction

    def at(self, t: float) -> Vec3:
        return self.origin + self.direction * t

    def __repr__(self) -> str:
        return f"Ray(origin={self.origin!r}, direction={self.direction!r})"
