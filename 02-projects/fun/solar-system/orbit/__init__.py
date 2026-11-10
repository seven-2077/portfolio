"""太阳系星历计算器：开普勒方程 → 行星真实位置。

公开 API：
    solve_kepler / true_anomaly     开普勒方程求解（orbit.kepler）
    ELEMENTS / elements_at          J2000 轨道根数表（orbit.elements）
    julian_day / datetime_to_jd     儒略日与历元换算（orbit.time_utils）
    heliocentric_lonlat / geocentric_lonlat / sun_lonlat / find_conjunction
                                    日心/地心黄经（orbit.planet）
    build_chart / save_chart        SVG 黄道带星图（orbit.chart）
"""

from .chart import build_chart, save_chart
from .elements import ELEMENTS, OrbitElements, elements_at
from .kepler import KeplerError, orbital_radius, solve_kepler, true_anomaly
from .planet import (
    ZODIAC,
    find_conjunction,
    geocentric_lonlat,
    geocentric_xyz,
    heliocentric_lonlat,
    heliocentric_xyz,
    separation,
    sun_lonlat,
    zodiac_of,
)
from .time_utils import (
    JD_B1900,
    JD_J1900,
    JD_J2000,
    centuries_since_j2000,
    datetime_to_jd,
    epoch_jd,
    jd_to_datetime,
    julian_day,
    parse_date,
)

__all__ = [
    "solve_kepler", "true_anomaly", "orbital_radius", "KeplerError",
    "ELEMENTS", "OrbitElements", "elements_at",
    "julian_day", "datetime_to_jd", "jd_to_datetime", "parse_date",
    "epoch_jd", "centuries_since_j2000", "JD_J1900", "JD_J2000", "JD_B1900",
    "heliocentric_xyz", "geocentric_xyz", "heliocentric_lonlat",
    "geocentric_lonlat", "sun_lonlat", "zodiac_of", "separation",
    "find_conjunction", "ZODIAC",
    "build_chart", "save_chart",
]
