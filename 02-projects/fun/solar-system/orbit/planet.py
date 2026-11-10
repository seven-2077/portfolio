"""由轨道根数 → 日心黄道直角坐标 → 黄经黄纬 → 地心位置。

流水线（完全按 JPL 近似历表的算法步骤）
----------------------------------------
1. 根数随历元推算：a, e, i, ω, Ω, M = f(T)（见 elements.elements_at）
2. 牛顿迭代解开普勒方程得偏近点角 E（kepler.solve_kepler）
3. 轨道面直角坐标：x' = a(cosE − e)，y' = a√(1−e²)·sinE
4. 三次旋转到 J2000 黄道（JPL 矩阵 R_z(−Ω)R_x(−I)R_z(−ω) 的展开式）
5. 日心黄道直角坐标 (x, y, z) → 黄经 λ = atan2(y, x)，黄纬 β = asin(z/r)
6. 地心 = 行星日心矢量 − 地球日心矢量；太阳地心黄经 = −地球日心黄经
"""

from __future__ import annotations

import math

from .elements import ELEMENTS, elements_at
from .kepler import solve_kepler
from .time_utils import centuries_since_j2000

__all__ = [
    "heliocentric_xyz",
    "geocentric_xyz",
    "heliocentric_lonlat",
    "geocentric_lonlat",
    "sun_lonlat",
    "zodiac_of",
    "separation",
    "find_conjunction",
]

# 黄道十二宫：起始黄经 / 中文名 / 符号
ZODIAC: tuple[tuple[str, str], ...] = (
    ("白羊", "\u2648"), ("金牛", "\u2649"), ("双子", "\u264a"),
    ("巨蟹", "\u264b"), ("狮子", "\u264c"), ("处女", "\u264d"),
    ("天秤", "\u264e"), ("天蝎", "\u264f"), ("射手", "\u2650"),
    ("摩羯", "\u2651"), ("水瓶", "\u2652"), ("双鱼", "\u2653"),
)


def _wrap360(deg: float) -> float:
    """归一到 [0, 360)。"""
    return deg % 360.0


def _wrap180(deg: float) -> float:
    """归一到 (−180, 180]，用于角距/差角。"""
    return math.remainder(deg, 360.0)


def _rot_to_ecliptic(xp: float, yp: float, omega: float, node: float,
                      inc_deg: float) -> tuple[float, float, float]:
    """轨道面坐标 (x', y') → J2000 黄道直角坐标 (x, y, z)，单位同输入。

    采用 JPL 近似历表给出的旋转展开式（与 R_z(−Ω)R_x(−I)R_z(−ω) 等价），
    omega/node 为弧度，inc_deg 为倾角（度）。
    """
    w, n = math.radians(omega), math.radians(node)
    inc = math.radians(inc_deg)
    cw, sw = math.cos(w), math.sin(w)
    cn, sn = math.cos(n), math.sin(n)
    ci, si = math.cos(inc), math.sin(inc)
    x = (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp
    y = (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def _lonlat(x: float, y: float, z: float) -> tuple[float, float]:
    """直角坐标 → (黄经 deg ∈ [0,360), 黄纬 deg)。零矢量返回 (nan, nan)。"""
    r = math.sqrt(x * x + y * y + z * z)
    if r == 0.0:
        return math.nan, math.nan
    lon = _wrap360(math.degrees(math.atan2(y, x)))
    lat = math.degrees(math.asin(max(-1.0, min(1.0, z / r))))
    return lon, lat


def heliocentric_xyz(key: str, jd: float) -> tuple[float, float, float]:
    """行星在给定 JD 的日心黄道直角坐标（AU，J2000 黄道框架）。"""
    el = elements_at(key, jd)
    M = math.radians(el.M0)                      # 平近点角（度→弧度）
    E = solve_kepler(M, el.e)                    # 开普勒方程数值解
    xp = el.a * (math.cos(E) - el.e)
    yp = el.a * math.sqrt(1.0 - el.e * el.e) * math.sin(E)
    return _rot_to_ecliptic(xp, yp, el.omega, el.node, el.i)


def geocentric_xyz(key: str, jd: float) -> tuple[float, float, float]:
    """地心（观测者）黄道直角坐标 = 行星日心矢量 − 地球日心矢量。"""
    px, py, pz = heliocentric_xyz(key, jd)
    ex, ey, ez = heliocentric_xyz("earth", jd)
    return px - ex, py - ey, pz - ez


def heliocentric_lonlat(key: str, jd: float) -> tuple[float, float]:
    """日心黄经黄纬（deg）。"""
    return _lonlat(*heliocentric_xyz(key, jd))


def geocentric_lonlat(key: str, jd: float) -> tuple[float, float]:
    """地心黄经黄纬（deg）——观星 App 展示的就是这个。"""
    return _lonlat(*geocentric_xyz(key, jd))


def sun_lonlat(jd: float) -> tuple[float, float]:
    """太阳的地心黄经黄纬（deg）：与地球日心位置恰好方向相反。"""
    x, y, z = heliocentric_xyz("earth", jd)
    return _lonlat(-x, -y, -z)


def zodiac_of(lon: float) -> tuple[str, str, float]:
    """黄经 → (星座中文名, 符号, 宫内度数)。例：115.78° → ('狮子', '♌', 25.78)。"""
    lon = _wrap360(lon)
    idx = int(lon // 30.0) % 12
    name, sym = ZODIAC[idx]
    return name, sym, lon - idx * 30.0


def separation(lon1: float, lon2: float) -> float:
    """两个黄经的角距（deg ∈ [0, 180]）。"""
    return abs(_wrap180(lon1 - lon2))


def find_conjunction(key_a: str, key_b: str, jd_center: float,
                     span_days: float = 15.0, step: float = 0.5) -> float | None:
    """在 jd_center ± span_days 内寻找两行星的地心黄经合（Δλ = 0）。

    扫描差角 f(jd) = wrap180(λa − λb) 的变号点（要求两侧 |f| < 30°，
    避免把"冲"误判为"合"），再二分至 1e-5 天（约 0.9 秒）。
    找不到返回 None。返回值为儒略日。
    """
    def f(jd: float) -> float:
        la, _ = geocentric_lonlat(key_a, jd)
        lb, _ = geocentric_lonlat(key_b, jd)
        return _wrap180(la - lb)

    jd0 = jd_center - span_days
    f0 = f(jd0)
    n = int(2.0 * span_days / step) + 1
    for i in range(1, n + 1):
        jd1 = min(jd0 + i * step, jd_center + span_days)
        f1 = f(jd1)
        if f0 == 0.0:
            return jd0
        if f1 == 0.0:
            return jd1
        if f0 * f1 < 0.0 and abs(f0) < 30.0 and abs(f1) < 30.0:
            lo, hi, flo = jd0, jd1, f0   # 保证 f(lo) 与 f(hi) 变号
            for _ in range(80):
                if hi - lo <= 1e-5:
                    break
                mid = 0.5 * (lo + hi)
                fmid = f(mid)
                if fmid == 0.0:
                    return mid
                if fmid * flo > 0.0:
                    lo, flo = mid, fmid
                else:
                    hi = mid
            return 0.5 * (lo + hi)
        jd0, f0 = jd1, f1
        if jd0 >= jd_center + span_days:
            break
    return None
