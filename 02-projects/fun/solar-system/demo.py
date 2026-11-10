#!/usr/bin/env python3
"""太阳系星历计算器 demo —— 开普勒方程算出的行星位置，和观星 App 对表。

用法
----
    python demo.py                 # 今天（UTC 当前时刻）
    python demo.py 1999-05-20      # 任意日期（取当日 12:00 UTC）
    python demo.py 1999-05-20 13:45  # 指定到分钟（UTC）

流程
----
a) 打印八行星黄经表（日心 / 地心 / 距离 / 所在星座）
b) 生成当日黄道星图 SVG → output/
c) 有参数时改为计算该日期
d) 对照两次已知天象（2026 金木合、2020 土木大合）打印偏差
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

# 允许从任意工作目录运行 demo.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orbit import (  # noqa: E402
    ELEMENTS,
    datetime_to_jd,
    find_conjunction,
    geocentric_lonlat,
    geocentric_xyz,
    heliocentric_lonlat,
    heliocentric_xyz,
    jd_to_datetime,
    parse_date,
    save_chart,
    sun_lonlat,
    zodiac_of,
)

OUT_DIR = Path(__file__).resolve().parent / "output"

# 已知天象对照：(描述, 行星A, 行星B, 实际时刻 UTC)
#   数据来源：SkyCaramba / timeanddate / In-The-Sky（地心黄经合）
EVENTS: list[tuple[str, str, str, dt.datetime]] = [
    ("2026-06-09 金星·木星地心合", "venus", "jupiter",
     dt.datetime(2026, 6, 9, 19, 48)),
    ("2020-12-21 木星·土星大合（397 年来最近）", "jupiter", "saturn",
     dt.datetime(2020, 12, 21, 18, 20)),
]


def _disp_len(s: str) -> int:
    """显示宽度（CJK 记 2 列），让中文表格对齐。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _disp_len(s))


def print_planet_table(jd: float) -> None:
    """a) 八行星 + 太阳的黄经表。"""
    print("=" * 74)
    print(f"黄经表 · {jd_to_datetime(jd):%Y-%m-%d %H:%M} UTC · JD {jd:.4f}")
    print("=" * 74)
    header = (_pad("行星", 12) + _pad("日心黄经", 11) + _pad("地心黄经", 11)
              + _pad("地心距离", 11) + "地心所在星座")
    print(header)
    print("-" * 74)

    for key, el in ELEMENTS.items():
        hlon, _ = heliocentric_lonlat(key, jd)
        name = f"{el.symbol} {el.name_cn}"
        if key == "earth":
            row = (_pad(name, 12) + _pad(f"{hlon:.2f}\u00b0", 11)
                   + _pad("\u2014（观测点）", 11) + _pad("\u2014", 11)
                   + "\u2014")
            print(row)
            continue
        glon, _ = geocentric_lonlat(key, jd)
        x, y, z = geocentric_xyz(key, jd)
        dist = math.sqrt(x * x + y * y + z * z)
        sign, sym, deg = zodiac_of(glon)
        row = (_pad(name, 12) + _pad(f"{hlon:.2f}\u00b0", 11)
               + _pad(f"{glon:.2f}\u00b0", 11)
               + _pad(f"{dist:.4f} AU", 11)
               + f"{sign}{sym} {deg:.1f}\u00b0")
        print(row)

    slon, _ = sun_lonlat(jd)
    sx, sy, sz = heliocentric_xyz("earth", jd)  # 太阳地心距离 = 地球日心距离
    sdist = math.sqrt(sx * sx + sy * sy + sz * sz)
    sign, sym, deg = zodiac_of(slon)
    row = (_pad("\u2609 太阳", 12) + _pad("\u2014", 11)
           + _pad(f"{slon:.2f}\u00b0", 11) + _pad(f"{sdist:.4f} AU", 11)
           + f"{sign}{sym} {deg:.1f}\u00b0")
    print(row)
    print("-" * 74)
    print("注：观星 App / 天文台展示的是「地心黄经」列；日心黄经用于轨道视角。")


def generate_chart(jd: float, when: dt.datetime) -> Path:
    """b/c) 生成当日黄道星图。"""
    path = OUT_DIR / f"zodiac_{when:%Y-%m-%d}.svg"
    save_chart(jd, path)
    return path


def check_events() -> None:
    """d) 已知天象对照：计算合日时刻 vs 权威星表。"""
    print("=" * 74)
    print("已知天象对照（合 = 两行星地心黄经相等）")
    print("=" * 74)
    for desc, a, b, real in EVENTS:
        jd_real = datetime_to_jd(real)
        jd_calc = find_conjunction(a, b, jd_real, span_days=15.0, step=0.5)
        print(f"\n{desc}")
        print(f"  实际（权威星表）：{real:%Y-%m-%d %H:%M} UTC")
        if jd_calc is None:
            print("  本项目计算：未在 ±15 天窗口内找到合")
            continue
        calc_dt = jd_to_datetime(jd_calc)
        delta_days = jd_calc - jd_real
        ok = abs(delta_days) < 3.0
        print(f"  本项目计算：{calc_dt:%Y-%m-%d %H:%M} UTC")
        print(f"  偏差：{delta_days:+.3f} 天（{delta_days * 24:+.1f} 小时）"
              f" → {'符合 ±3 天判据 ✅' if ok else '超出 ±3 天 ❌'}")
    print("\n说明：本项目用 J2000 根数 + 一阶长期项的简化历表，")
    print("      黄经误差量级约 ±1°，合日偏差通常在数小时内～数天。")


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print(__doc__)
        return 2

    if len(argv) == 1:
        when = parse_date(argv[0])
        if len(argv[0]) == 10:          # 只给日期 → 取当日 12:00 UTC
            when = when.replace(hour=12)
        print(f"计算日期：{argv[0]}（按 UTC 解释"
              f"{'，取正午' if len(argv[0]) == 10 else ''}）")
    else:
        when = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        print("未指定日期 → 计算现在（UTC 当前时刻）")

    jd = datetime_to_jd(when)
    print_planet_table(jd)

    path = generate_chart(jd, when)
    print(f"\n黄道星图已生成：{path}")

    check_events()
    print("\n小提示：换任意日期试试 —— python demo.py 1999-05-20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
