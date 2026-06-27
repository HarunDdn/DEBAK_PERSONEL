"""CANIAS CALENDAR / HCMSVRN tarih fonksiyonlarinin Python karsiliklari.

Bu fonksiyonlar trace dosyasindaki davranisi birebir taklit eder:
  - CALREC.GETYEARDIFF
  - ADDDAYS / ADDYEARS / SUBYEARS
  - HCMSVRNREC.GETDATEDIFF  (KYEAR/KMONTH/KDAY)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple


def add_days(d: date, days: float) -> date:
    """ADDDAYS(d, days). Ondalik gun degeri tam sayiya yuvarlanir (gun bazli)."""
    return d + timedelta(days=int(round(days)))


def _set_year(d: date, year: int) -> date:
    """Yil degistirir; 29 Subat gibi gecersiz tarihleri 28'e sabitler."""
    try:
        return d.replace(year=year)
    except ValueError:
        # 29.02 -> 28.02 (artik olmayan yil)
        return d.replace(year=year, day=28)


def add_years(d: date, years: int) -> date:
    """ADDYEARS(d, years)."""
    return _set_year(d, d.year + int(years))


def sub_years(d: date, years: int) -> date:
    """SUBYEARS(d, years)."""
    return _set_year(d, d.year - int(years))


def get_year_diff(dt1: date, dt2: date) -> int:
    """CALREC.GETYEARDIFF(dt1, dt2) birebir kopyasi.

    Trace mantigi:
        YEARCOUNT = year(dt2) - year(dt1)
        if month1 > month2 or (month1 == month2 and day1 > day2):
            YEARCOUNT -= 1
    """
    month1, month2 = dt1.month, dt2.month
    day1, day2 = dt1.day, dt2.day
    year_count = dt2.year - dt1.year
    if (month1 > month2) or (month1 == month2 and day1 > day2):
        year_count -= 1
    return year_count


def svrn_date_diff(dt1: date, dt2: date, misday: int = 0) -> Tuple[int, int, int]:
    """HCMSVRNREC.GETDATEDIFF(dt1, dt2, misday) -> (KYEAR, KMONTH, KDAY).

    CALCEXCLUDEDSEN icinde kidem ayini bulmak icin kullanilir.
    Trace adimlari (HCMSVRNREC.GETDATEDIFF.0):
        TMPDATE = ADDDAYS(dt2, -misday)
        if dt1 > TMPDATE: (ters durum) -> 0,0,0
        KDAY: day2 >= day1 ? day2-day1+1 : (onceki ay gunu tamamla)
        KMONTH: month2 >= month1 ? month2-month1 : month2-month1+12 (yil dusur)
        KYEAR = year2 - year1 (gerekirse gun/ay tasmasi ile duzeltilir)
    """
    tmpdate = add_days(dt2, -misday)
    if dt1 > tmpdate:
        return 0, 0, 0

    year1, month1, day1 = dt1.year, dt1.month, dt1.day
    year2, month2, day2 = tmpdate.year, tmpdate.month, tmpdate.day
    first_day = day1
    last_month = month2
    last_day = day2

    kyear = 0
    kmonth = 0
    kday = 0

    if day2 >= day1:
        kday = day2 - day1 + 1
    else:
        # Onceki aydan gun odunc al (basit 30 gunluk model degil; gercek ay uzunlugu)
        prev_month = month2 - 1 or 12
        prev_year = year2 if month2 != 1 else year2 - 1
        days_in_prev = _days_in_month(prev_year, prev_month)
        kday = days_in_prev - day1 + day2 + 1
        month2 -= 1
        if month2 == 0:
            month2 = 12
            year2 -= 1

    if month2 >= month1:
        kmonth = month2 - month1
    else:
        kmonth = month2 - month1 + 12
        year2 -= 1

    kyear = year2 - year1

    # KDAY >= 30 ise (veya Subat sonu ozel durumu) bir aya yuvarla
    if kday >= 30 or (last_month == 2 and last_day == 28 and first_day == 1):
        kday = 0
        kmonth += 1
    if kmonth >= 12:
        kmonth -= 12
        kyear += 1

    return kyear, kmonth, kday


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days
