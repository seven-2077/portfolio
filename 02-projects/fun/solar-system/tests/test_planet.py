"""行星位置测试：太阳黄经、取值范围、近日点几何、已知合日对照。"""

import math
import unittest
from datetime import datetime

from orbit.elements import ELEMENTS, elements_at
from orbit.planet import (
    find_conjunction,
    geocentric_lonlat,
    geocentric_xyz,
    heliocentric_lonlat,
    heliocentric_xyz,
    separation,
    sun_lonlat,
    zodiac_of,
)
from orbit.time_utils import JD_J2000, datetime_to_jd

_JD_J2000 = datetime_to_jd(datetime(2000, 1, 1, 12))
assert _JD_J2000 == JD_J2000


class TestSunAndEarth(unittest.TestCase):
    def test_sun_longitude_at_j2000(self):
        """2000-01-01 12:00 太阳黄经 ≈ 280.46°（题目要求 ±2°）。"""
        lon, lat = sun_lonlat(_JD_J2000)
        self.assertAlmostEqual(lon, 280.46, delta=2.0)
        self.assertAlmostEqual(lat, 0.0, delta=0.05)

    def test_sun_opposite_to_earth(self):
        """太阳地心黄经 = 地球日心黄经 + 180°（方向恒相反）。"""
        for jd in (2451517.5, 2455555.5, 2461000.5, 2461349.5):
            slon, _ = sun_lonlat(jd)
            elon, _ = heliocentric_lonlat("earth", jd)
            self.assertAlmostEqual(slon, (elon + 180.0) % 360.0, delta=1e-9)

    def test_earth_heliocentric_longitude_j2000(self):
        """J2000 时地球日心黄经 ≈ 100.46°。"""
        lon, _ = heliocentric_lonlat("earth", _JD_J2000)
        self.assertAlmostEqual(lon, 100.46, delta=1.0)


class TestLongitudeRanges(unittest.TestCase):
    def test_heliocentric_range_grid(self):
        """1990–2040 抽样：日心黄经 ∈ [0,360)，黄纬 ∈ [-90,90]。"""
        for year in range(1990, 2041, 5):
            jd = datetime_to_jd(datetime(year, 6, 15, 12))
            for key in ELEMENTS:
                lon, lat = heliocentric_lonlat(key, jd)
                self.assertGreaterEqual(lon, 0.0)
                self.assertLess(lon, 360.0)
                self.assertGreaterEqual(lat, -90.0)
                self.assertLessEqual(lat, 90.0)

    def test_geocentric_range_grid(self):
        """地心黄经 ∈ [0,360)（七颗外显行星），地球为观测点返回 NaN。"""
        for year in range(1990, 2041, 5):
            jd = datetime_to_jd(datetime(year, 6, 15, 12))
            for key in ELEMENTS:
                lon, lat = geocentric_lonlat(key, jd)
                if key == "earth":
                    self.assertTrue(math.isnan(lon))
                    continue
                self.assertGreaterEqual(lon, 0.0, key)
                self.assertLess(lon, 360.0, key)
                self.assertGreaterEqual(lat, -90.0)
                self.assertLessEqual(lat, 90.0)

    def test_geocentric_is_vector_difference(self):
        """地心矢量 = 行星日心矢量 − 地球日心矢量（恒等式）。"""
        jd = datetime_to_jd(datetime(2026, 6, 9, 12))
        px, py, pz = heliocentric_xyz("venus", jd)
        ex, ey, ez = heliocentric_xyz("earth", jd)
        gx, gy, gz = geocentric_xyz("venus", jd)
        self.assertAlmostEqual(gx, px - ex, places=12)
        self.assertAlmostEqual(gy, py - ey, places=12)
        self.assertAlmostEqual(gz, pz - ez, places=12)

    def test_earth_geocentric_is_origin(self):
        jd = datetime_to_jd(datetime(2026, 6, 9, 12))
        self.assertEqual(geocentric_xyz("earth", jd), (0.0, 0.0, 0.0))


class TestPerihelionAphelionGeometry(unittest.TestCase):
    def _extreme_times(self, key: str):
        """由 M(T) = 0 / 180° 反解近日点、远日点时刻。"""
        el = ELEMENTS[key]
        t_peri = -el.M0 / el.M_dot
        t_aph = (180.0 - el.M0) / el.M_dot
        from orbit.time_utils import JD_J2000
        return JD_J2000 + t_peri * 36525.0, JD_J2000 + t_aph * 36525.0

    @staticmethod
    def _perihelion_lon(el) -> float:
        """近日点投影到黄道的真实黄经。

        注意 ϖ = ω + Ω 只是角度和；轨道有倾角 i 时，实际黄经为
        λ = Ω + atan2(sin ω · cos i, cos ω)，两者相差 i·sin ω 量级
        （水星约 0.18°）——这正是旋转矩阵该做的事。
        """
        inc = math.radians(el.i)
        u = math.radians(el.omega)
        delta = math.degrees(math.atan2(math.sin(u) * math.cos(inc),
                                        math.cos(u)))
        return (el.node + delta) % 360.0

    def test_mercury_perihelion(self):
        """水星过近日点：r = a(1−e)，方向 = 近日点投影黄经。"""
        key = "mercury"
        jd_peri, _ = self._extreme_times(key)
        el = elements_at(key, jd_peri)
        x, y, z = heliocentric_xyz(key, jd_peri)
        r = math.sqrt(x * x + y * y + z * z)
        lon = math.degrees(math.atan2(y, x)) % 360.0
        self.assertAlmostEqual(r, el.a * (1.0 - el.e), places=9)
        self.assertAlmostEqual(lon, self._perihelion_lon(el), delta=1e-6)

    def test_mercury_aphelion(self):
        """水星过远日点：r = a(1+e)，方向 = 近日点黄经 + 180°。"""
        key = "mercury"
        _, jd_aph = self._extreme_times(key)
        el = elements_at(key, jd_aph)
        x, y, z = heliocentric_xyz(key, jd_aph)
        r = math.sqrt(x * x + y * y + z * z)
        lon = math.degrees(math.atan2(y, x)) % 360.0
        self.assertAlmostEqual(r, el.a * (1.0 + el.e), places=9)
        self.assertAlmostEqual(lon,
                               (self._perihelion_lon(el) + 180.0) % 360.0,
                               delta=1e-6)

    def test_earth_aphelion_july(self):
        """地球远日点在 7 月初：7 月 4 日前后 r 达到最大。"""
        r_jan = self._earth_r(datetime_to_jd(datetime(2026, 1, 4, 12)))
        r_jul = self._earth_r(datetime_to_jd(datetime(2026, 7, 4, 12)))
        self.assertGreater(r_jul, r_jan)
        self.assertAlmostEqual(r_jul, 1.0167, delta=0.001)

    @staticmethod
    def _earth_r(jd: float) -> float:
        x, y, z = heliocentric_xyz("earth", jd)
        return math.sqrt(x * x + y * y + z * z)


class TestKnownConjunctions(unittest.TestCase):
    def test_venus_jupiter_2026(self):
        """2026-06-09 19:48 UTC 金木合：计算值须落在 ±3 天内。"""
        real = datetime_to_jd(datetime(2026, 6, 9, 19, 48))
        calc = find_conjunction("venus", "jupiter", real,
                                span_days=15.0, step=0.5)
        self.assertIsNotNone(calc)
        self.assertLess(abs(calc - real), 3.0,
                        f"偏差 {calc - real:.3f} 天超出 ±3 天")

    def test_jupiter_saturn_2020(self):
        """2020-12-21 18:20 UTC 土木大合：计算值须落在 ±3 天内。"""
        real = datetime_to_jd(datetime(2020, 12, 21, 18, 20))
        calc = find_conjunction("jupiter", "saturn", real,
                                span_days=15.0, step=0.5)
        self.assertIsNotNone(calc)
        self.assertLess(abs(calc - real), 3.0,
                        f"偏差 {calc - real:.3f} 天超出 ±3 天")

    def test_conjunction_returns_none_when_absent(self):
        """窗口内没有合时返回 None（不误报）。"""
        # 2026-06-09 附近木星-土星角距 > 40°，窗口内不可能合
        real = datetime_to_jd(datetime(2026, 6, 9, 19, 48))
        self.assertIsNone(find_conjunction("jupiter", "saturn", real,
                                           span_days=15.0, step=0.5))


class TestZodiacHelpers(unittest.TestCase):
    def test_sign_boundaries(self):
        name, sym, deg = zodiac_of(0.0)
        self.assertEqual(name, "白羊")
        self.assertEqual(deg, 0.0)
        name, _, deg = zodiac_of(359.9)
        self.assertEqual(name, "双鱼")
        self.assertAlmostEqual(deg, 29.9, places=6)

    def test_known_longitude(self):
        """115.78° = 25°47′ 巨蟹（2026 金木合所在位置，CA = Cancer）。"""
        name, _, deg = zodiac_of(115.78)
        self.assertEqual(name, "巨蟹")
        self.assertAlmostEqual(deg, 25.78, places=6)

    def test_separation_wrap(self):
        self.assertAlmostEqual(separation(350.0, 10.0), 20.0)
        self.assertAlmostEqual(separation(10.0, 350.0), 20.0)
        self.assertAlmostEqual(separation(0.0, 180.0), 180.0)


if __name__ == "__main__":
    unittest.main()
