"""J2000 历元轨道根数表（八行星）。

数据来源（已对照原站核验）
--------------------------
JPL SSD《Approximate Positions of the Planets》Table 1：
https://ssd.jpl.nasa.gov/planets/approx_pos.html
（E. M. Standish & J. G. Williams, 1992）

原表给出六个根数 a、e、I、L（平黄经）、ϖ（近日点黄经）、Ω（升交点黄经）
及其每儒勒世纪（36525 天）长期项，历元 J2000.0，适用时段 1800–2050 AD；
该页 Accuracy 表给出本近似的误差：日心黄经 10″–600″（外行星摄动被拟合
吸收了一部分，残差仍是角分级别，详见 README 精度声明）。

按本项目要求收纳/换算的字段
--------------------------
- a      半长轴（AU）
- e      偏心率
- i      轨道倾角（deg，相对黄道）
- omega  近日点幅角 ω = ϖ − Ω（deg）
- node   升交点经度 Ω（deg）
- M0     J2000 平近点角 M₀ = L − ϖ（deg）
- period_days 公转周期（天），由平近点角速率换算：
      P = 36525 × 360 / Ṁ，Ṁ = L̇ − ϖ̇（deg/儒勒世纪）
- 另附一阶长期项 a_dot/e_dot/i_dot/omega_dot/node_dot/M_dot（单位 /世纪），
  供 elements_at() 把根数推算到任意历元。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .time_utils import centuries_since_j2000

__all__ = ["OrbitElements", "ELEMENTS", "elements_at", "PLANET_KEYS"]

# key -> 中文名 / 英文名 / 天文符号
_META: dict[str, tuple[str, str, str]] = {
    "mercury": ("水星", "Mercury", "\u263f"),   # ☿
    "venus": ("金星", "Venus", "\u2640"),       # ♀
    "earth": ("地球", "Earth (EM barycenter)", "\u2641"),  # ♁
    "mars": ("火星", "Mars", "\u2642"),         # ♂
    "jupiter": ("木星", "Jupiter", "\u2643"),   # ♃
    "saturn": ("土星", "Saturn", "\u2644"),     # ♄
    "uranus": ("天王星", "Uranus", "\u2645"),   # ♅
    "neptune": ("海王星", "Neptune", "\u2646"),  # ♆
}

# JPL SSD Table 1 原始数据（J2000.0，1800–2050 AD）
# 字段：a[au], e, I[deg], L[deg], 近日点黄经 ϖ[deg], 升交点黄经 Ω[deg]
# 及其每儒勒世纪长期项（*_dot）
_JPL_TABLE1: dict[str, dict[str, float]] = {
    "mercury": dict(
        a=0.38709927, a_dot=0.00000037,
        e=0.20563593, e_dot=0.00001906,
        i=7.00497902, i_dot=-0.00594749,
        L=252.25032350, L_dot=149472.67411175,
        peri=77.45779628, peri_dot=0.16047689,
        node=48.33076593, node_dot=-0.12534081,
    ),
    "venus": dict(
        a=0.72333566, a_dot=0.00000390,
        e=0.00677672, e_dot=-0.00004107,
        i=3.39467605, i_dot=-0.00078890,
        L=181.97909950, L_dot=58517.81538729,
        peri=131.60246718, peri_dot=0.00268329,
        node=76.67984255, node_dot=-0.27769418,
    ),
    "earth": dict(
        a=1.00000261, a_dot=0.00000562,
        e=0.01671123, e_dot=-0.00004392,
        i=-0.00001531, i_dot=-0.01294668,
        L=100.46457166, L_dot=35999.37244981,
        peri=102.93768193, peri_dot=0.32327364,
        node=0.0, node_dot=0.0,
    ),
    "mars": dict(
        a=1.52371034, a_dot=0.00001847,
        e=0.09339410, e_dot=0.00007882,
        i=1.84969142, i_dot=-0.00813131,
        L=-4.55343205, L_dot=19140.30268499,
        peri=-23.94362959, peri_dot=0.44441088,
        node=49.55953891, node_dot=-0.29257343,
    ),
    "jupiter": dict(
        a=5.20288700, a_dot=-0.00011607,
        e=0.04838624, e_dot=-0.00013253,
        i=1.30439695, i_dot=-0.00183714,
        L=34.39644051, L_dot=3034.74612775,
        peri=14.72847983, peri_dot=0.21252668,
        node=100.47390909, node_dot=0.20469106,
    ),
    "saturn": dict(
        a=9.53667594, a_dot=-0.00125060,
        e=0.05386179, e_dot=-0.00050991,
        i=2.48599187, i_dot=0.00193609,
        L=49.95424423, L_dot=1222.49362201,
        peri=92.59887831, peri_dot=-0.41897216,
        node=113.66242448, node_dot=-0.28867794,
    ),
    "uranus": dict(
        a=19.18916464, a_dot=-0.00196176,
        e=0.04725744, e_dot=-0.00004397,
        i=0.77263783, i_dot=-0.00242939,
        L=313.23810451, L_dot=428.48202785,
        peri=170.95427630, peri_dot=0.40805281,
        node=74.01692503, node_dot=0.04240589,
    ),
    "neptune": dict(
        a=30.06992276, a_dot=0.00026291,
        e=0.00859048, e_dot=0.00005105,
        i=1.77004347, i_dot=0.00035372,
        L=-55.12002969, L_dot=218.45945325,
        peri=44.96476227, peri_dot=-0.32241464,
        node=131.78422574, node_dot=-0.00508664,
    ),
}


@dataclass(frozen=True)
class OrbitElements:
    """某一历元的六根数 + 额外元数据（dataclass 冻结，随历元推算用 replace）。"""

    key: str
    name_cn: str
    name_en: str
    symbol: str
    a: float            # 半长轴 AU
    e: float            # 偏心率
    i: float            # 轨道倾角 deg
    omega: float        # 近日点幅角 ω deg（J2000）
    node: float         # 升交点经度 Ω deg（J2000）
    M0: float           # 平近点角 deg（J2000）
    period_days: float  # 公转周期（天）
    # 一阶长期项（/儒勒世纪）
    a_dot: float
    e_dot: float
    i_dot: float
    omega_dot: float
    node_dot: float
    M_dot: float

    @property
    def period_years(self) -> float:
        """公转周期（儒勒年，1 年 = 365.25 天）。"""
        return self.period_days / 365.25


def _build() -> dict[str, OrbitElements]:
    out: dict[str, OrbitElements] = {}
    for key, (cn, en, sym) in _META.items():
        r = _JPL_TABLE1[key]
        M0 = r["L"] - r["peri"]                       # M₀ = L − ϖ
        omega = r["peri"] - r["node"]                 # ω = ϖ − Ω
        M_dot = r["L_dot"] - r["peri_dot"]            # Ṁ = L̇ − ϖ̇ (deg/century)
        omega_dot = r["peri_dot"] - r["node_dot"]     # ω̇ = ϖ̇ − Ω̇
        period_days = 36525.0 * 360.0 / M_dot         # P = 36525×360/Ṁ
        out[key] = OrbitElements(
            key=key, name_cn=cn, name_en=en, symbol=sym,
            a=r["a"], e=r["e"], i=r["i"],
            omega=omega, node=r["node"], M0=M0, period_days=period_days,
            a_dot=r["a_dot"], e_dot=r["e_dot"], i_dot=r["i_dot"],
            omega_dot=omega_dot, node_dot=r["node_dot"], M_dot=M_dot,
        )
    return out


#: 八行星根数表（key → OrbitElements），按距日远近排序
ELEMENTS: dict[str, OrbitElements] = _build()

#: 表内顺序（demo 打印用）
PLANET_KEYS: tuple[str, ...] = tuple(_META.keys())


def elements_at(key: str, jd: float) -> OrbitElements:
    """把 J2000 根数用一阶长期项推算到给定儒略日对应的历元。

    T = (jd − 2451545.0) / 36525（儒勒世纪），六个根数线性外推：
    a = a₀ + ȧT，e = e₀ + ėT，…，M = M₀ + ṀT。
    """
    el = ELEMENTS[key]
    T = centuries_since_j2000(jd)
    return replace(
        el,
        a=el.a + el.a_dot * T,
        e=el.e + el.e_dot * T,
        i=el.i + el.i_dot * T,
        omega=el.omega + el.omega_dot * T,
        node=el.node + el.node_dot * T,
        M0=el.M0 + el.M_dot * T,
    )
