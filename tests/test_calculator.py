"""Hesaplama motorunun trace senaryosuyla (PERSID 1028) dogrulanmasi.

Beklenen sonuc (trace HCMT101D001.GETREMAININGDAYS):
    REM1 = 3.0   (Diger Ucretsiz Izin / GR08)
    REM2 = 20.0  (Yillik Izin / GR01)
    REM3 = 3.0   (Hastalik Izni (Odemesiz) / GR08)
    REM4 = 3.0   (Ucretli Mazeret Izni / GR08)
"""
from datetime import date

from app.canias_leave import LeaveCalculator
from app.constants import GR01_ANNUAL_LEAVE_BRACKETS
from app.models import (
    HCM213Settings,
    LeaveGroupRow,
    LeaveRecord,
    PersonnelMaster,
)
from tests.fakes import FakeProvider

LVDATE = date(2026, 6, 26)  # Trace: PLVDATE = 26.06.2026


def _build_provider() -> FakeProvider:
    master = PersonnelMaster(
        persid="1028",
        contactnum="000000000029",
        company="01",
        plant="01",
        birthday=date(1983, 7, 24),
        display="Test Personel",
    )

    leave_groups = [
        # ANA SORGU ORDER BY LEAVECODE sirasi
        LeaveGroupRow("0003", "GR08", date(2025, 5, 25), usedday=0, extrayear=0,
                      stext="Diger Ucretsiz Izin"),
        LeaveGroupRow("0005", "GR01", date(2015, 5, 12), usedday=95, extrayear=0,
                      stext="Yillik Izin"),
        LeaveGroupRow("0008", "GR08", date(2025, 5, 25), usedday=0, extrayear=0,
                      stext="Hastalik Izni (Odemesiz)"),
        LeaveGroupRow("0009", "GR08", date(2025, 5, 25), usedday=0, extrayear=0,
                      stext="Ucretli Mazeret Izni"),
    ]

    hcm213 = {
        # Sabit izin grubu: gunde 3 gun, gun devri yok
        "GR08": HCM213Settings(
            lvgroupid="GR08", lvgrptype=0, daytransfer=False, isdatebased=False,
            lvdays=3.0, monthdays=0.0, firstlvmonth=0,
        ),
        # Yillik izin: yil bazli, gun devri var, kidem dilimleri
        "GR01": HCM213Settings(
            lvgroupid="GR01", lvgrptype=1, daytransfer=True, isdatebased=False,
            lvdays=0.0,
            brackets=list(GR01_ANNUAL_LEAVE_BRACKETS),
        ),
    }

    # Yillik izinde donem icinde kullanilan toplam 75 gun (trace: LVDAYS=75)
    leaves = {
        "0005": [
            LeaveRecord(date(2016, 1, 1), date(2016, 1, 30), 30.0),
            LeaveRecord(date(2018, 1, 1), date(2018, 1, 25), 25.0),
            LeaveRecord(date(2020, 1, 1), date(2020, 1, 20), 20.0),
        ],
    }

    return FakeProvider(master, leave_groups, hcm213, leaves=leaves)


def test_remaining_days_matches_trace():
    calc = LeaveCalculator(_build_provider(), as_of=LVDATE)
    results = calc.get_remaining_days("1028")

    rem = {r.index: r.remaining_days for r in results}
    assert rem[1] == 3.0   # REM1
    assert rem[2] == 20.0  # REM2 (Yillik Izin)
    assert rem[3] == 3.0   # REM3
    assert rem[4] == 3.0   # REM4


def test_annual_leave_components():
    calc = LeaveCalculator(_build_provider(), as_of=LVDATE)
    results = calc.get_remaining_days("1028")
    annual = next(r for r in results if r.leavegrp == "GR01")
    # Trace: TOTEARNED=190, LVDAYS=75, USEDDAY=95, SENYEAR=11
    assert annual.earned_days == 190.0
    assert annual.used_in_period == 75.0
    assert annual.carried_used == 95.0
    assert annual.seniority_years == 11


def test_field_names_and_order():
    calc = LeaveCalculator(_build_provider(), as_of=LVDATE)
    results = calc.get_remaining_days("1028")
    assert [r.name for r in results][1] == "Yillik Izin"
    assert results[0].leavecode == "0003"
