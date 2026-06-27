"""CANIAS takvim fonksiyonlarinin testleri (trace degerleriyle)."""
from datetime import date

from app import calendar_utils as cal


def test_get_year_diff_basic():
    # Trace: GETYEARDIFF(25.05.2025, 26.06.2026) = 1
    assert cal.get_year_diff(date(2025, 5, 25), date(2026, 6, 26)) == 1
    # Trace: GETYEARDIFF(12.05.2015, 26.06.2026) = 11
    assert cal.get_year_diff(date(2015, 5, 12), date(2026, 6, 26)) == 11


def test_get_year_diff_month_day_decrement():
    # 24.07.1983 -> 12.05.2019: yil farki 36 ama 07>05 oldugu icin 35
    assert cal.get_year_diff(date(1983, 7, 24), date(2019, 5, 12)) == 35


def test_add_days_and_years():
    assert cal.add_days(date(2025, 5, 2), 23) == date(2025, 5, 25)
    assert cal.add_days(date(2015, 4, 13), 29) == date(2015, 5, 12)
    assert cal.add_years(date(2025, 5, 25), 1) == date(2026, 5, 25)
    assert cal.sub_years(date(2025, 5, 25), 0) == date(2025, 5, 25)


def test_add_years_leap_day():
    assert cal.add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)
