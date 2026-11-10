"""时间工具测试：儒略日、1900/2000 历元、时区处理。"""

import unittest
from datetime import datetime, timedelta, timezone

from orbit.time_utils import (
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


class TestJulianDay(unittest.TestCase):
    def test_j2000_noon(self):
        """2000-01-01 12:00 TT = JD 2451545.0（题目指定的对照值）。"""
        self.assertAlmostEqual(datetime_to_jd(datetime(2000, 1, 1, 12)),
                               2451545.0, places=9)

    def test_j2000_midnight(self):
        self.assertAlmostEqual(datetime_to_jd(datetime(2000, 1, 1, 0)),
                               2451544.5, places=9)

    def test_1999_new_year(self):
        """JD 2451179.5 = 1999-01-01 00:00（比 2000-01-01 早整整 365 天）。"""
        self.assertAlmostEqual(julian_day(1999, 1, 1), 2451179.5, places=9)

    def test_1987_meeus_example(self):
        """Meeus《Astronomical Algorithms》例：1987-01-27 00:00 = 2446822.5。"""
        self.assertAlmostEqual(datetime_to_jd(datetime(1987, 1, 27)),
                               2446822.5, places=9)

    def test_fractional_day(self):
        """julian_day 支持小数日：1.5 表示该日正午。"""
        self.assertAlmostEqual(julian_day(2000, 1, 1.5), 2451545.0, places=9)


class TestEpochConversion(unittest.TestCase):
    def test_j2000_epoch(self):
        self.assertEqual(JD_J2000, 2451545.0)
        self.assertEqual(epoch_jd(2000), 2451545.0)

    def test_j1900_vs_b1900(self):
        """J1900 = 1900-01-01 12:00，贝塞尔历元 B1900 早整整一天。"""
        self.assertEqual(JD_J1900, 2415021.0)
        self.assertEqual(JD_B1900, 2415020.0)
        self.assertEqual(JD_J1900 - JD_B1900, 1.0)
        self.assertEqual(epoch_jd(1900), JD_J1900)

    def test_hundred_year_gap(self):
        """1900→2000 相差 36524 天（1900 年不是闰年，只有 24 个闰日）。"""
        self.assertEqual(epoch_jd(2000) - epoch_jd(1900), 36524.0)

    def test_centuries_since_j2000(self):
        self.assertEqual(centuries_since_j2000(2451545.0), 0.0)
        self.assertAlmostEqual(centuries_since_j2000(2451545.0 + 36525.0),
                               1.0, places=12)


class TestTimeZoneHandling(unittest.TestCase):
    def test_naive_treated_as_utc(self):
        """约定：naive datetime 按 UTC 解释。"""
        self.assertEqual(datetime_to_jd(datetime(2000, 1, 1, 12)), JD_J2000)

    def test_aware_converted_to_utc(self):
        """UTC+8 的 20:00 = UTC 的 12:00 → 同一 JD。"""
        dt_cn = datetime(2000, 1, 1, 20, 0,
                         tzinfo=timezone(timedelta(hours=8)))
        self.assertAlmostEqual(datetime_to_jd(dt_cn), JD_J2000, places=9)

    def test_roundtrip(self):
        """datetime → JD → datetime 往返一致（50 毫秒精度内）。"""
        dt0 = datetime(1999, 5, 20, 13, 45, 30)
        dt1 = jd_to_datetime(datetime_to_jd(dt0))
        self.assertLess(abs((dt1 - dt0).total_seconds()), 0.05)


class TestParseDate(unittest.TestCase):
    def test_date_only(self):
        self.assertEqual(parse_date("1999-05-20"), datetime(1999, 5, 20))

    def test_date_time(self):
        self.assertEqual(parse_date("1999-05-20 13:45"),
                         datetime(1999, 5, 20, 13, 45))
        self.assertEqual(parse_date("1999-05-20T13:45:30"),
                         datetime(1999, 5, 20, 13, 45, 30))

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_date("1999/05/20")
        with self.assertRaises(ValueError):
            parse_date("not a date")


if __name__ == "__main__":
    unittest.main()
