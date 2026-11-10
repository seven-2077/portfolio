"""时间工具：公历 ↔ 儒略日（JD），1900/2000 历元换算与时区约定。

儒略日是从公元前 4713-01-01 正午起算的连续日计数，
天文学家用它绕开历法混乱（闰年、历法改革、时区差异）。

1900 / 2000 历元换算
--------------------
- **J2000.0**（Julian epoch 2000）= 2000-01-01 12:00 TT = JD 2451545.0。
  本项目所有轨道根数都以它为基准——所谓"J2000 根数"即此。
- **J1900.0**（Julian epoch 1900）= 1900-01-01 12:00 = JD 2415021.0。
- 容易混淆的 **B1900.0**（Besselian epoch）= 1899-12-31 12:00 = JD 2415020.0，
  比 J1900.0 正好早 1 天——1900 年前后文献里的历元差异多半源于此。
  另外 1900-01-01 00:00 UT = JD 2415020.5，也常在旧书里出现。

时区处理约定
------------
- naive datetime（无 tzinfo）一律按 **UTC** 解释（本项目约定，避免
  "同一份代码在不同时区算出不同星历"）；
- aware datetime 先转换为 UTC 再算 JD；
- 天文上严格应使用力学时 TT = UT + ΔT（2026 年 ΔT ≈ +72 s）。
  本项目直接用 UT ≈ TT：72 s 对黄经的影响 < 0.0001°，可忽略。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

__all__ = [
    "JD_J1900",
    "JD_J2000",
    "JD_B1900",
    "julian_day",
    "datetime_to_jd",
    "jd_to_datetime",
    "parse_date",
    "epoch_jd",
    "centuries_since_j2000",
]

JD_J2000 = 2451545.0  # J2000.0：2000-01-01 12:00 TT
JD_J1900 = 2415021.0  # J1900.0：1900-01-01 12:00
JD_B1900 = 2415020.0  # B1900.0：1899-12-31 12:00（贝塞尔历元，比 J1900 早 1 天）


def julian_day(year: int, month: int, day: float) -> float:
    """公历日期 → 当日 0h 起算的儒略日（day 可带小数，1.5 表示该日 12:00）。

    算法为 Meeus《Astronomical Algorithms》第 7 章的公历-儒略日换算
    （等价于 Fliegel–Van Flandern 公式）。
    """
    d_int = int(math.floor(day))
    frac = day - d_int
    y, m = year, month
    if m <= 2:  # 1、2 月归入上一年的 13、14 月
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4  # 1582-10-15 格里历改历修正项
    jd = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + d_int
        + B
        - 1524.5
    )
    return jd + frac


def datetime_to_jd(dt: datetime) -> float:
    """datetime → 儒略日。naive 按 UTC 解释；aware 先转 UTC（见模块说明）。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    jd = julian_day(dt.year, dt.month, dt.day)
    frac = (
        dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond * 1e-6
    ) / 86400.0
    return jd + frac


def jd_to_datetime(jd: float) -> datetime:
    """儒略日 → naive UTC datetime（与 datetime_to_jd 互逆）。"""
    # JD 2451544.5 = 2000-01-01 00:00 UTC
    return datetime(2000, 1, 1) + timedelta(days=jd - 2451544.5)


def parse_date(s: str) -> datetime:
    """解析日期参数，支持：

    - ``1999-05-20``
    - ``1999-05-20 13:45``
    - ``1999-05-20T13:45:30``

    返回 naive datetime（按约定解释为 UTC）。格式不符抛 ValueError。
    """
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"无法解析日期 {s!r}，请使用 YYYY-MM-DD 或 'YYYY-MM-DD HH:MM' 格式"
    )


def epoch_jd(year: int) -> float:
    """儒勒历元（Julian epoch）的儒略日：year 年 1 月 1 日 12:00。

    epoch_jd(2000) == 2451545.0（J2000.0）
    epoch_jd(1900) == 2415021.0（J1900.0；注意贝塞尔历元 B1900.0 是 2415020.0）
    """
    return julian_day(year, 1, 1) + 0.5


def centuries_since_j2000(jd: float) -> float:
    """JD → 距 J2000.0 的儒勒世纪数 T = (JD - 2451545.0) / 36525。"""
    return (jd - JD_J2000) / 36525.0
