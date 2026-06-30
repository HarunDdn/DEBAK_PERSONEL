"""CALCEXCLUDEDSEN (kidem disi gun) hesabinin testleri."""
from datetime import date

from app.canias_leave import LeaveCalculator
from app.models import IHBDayBracket, LeaveRecord, PersonnelMaster
from tests.fakes import FakeProvider


def _calc(excsenlv, excluded, ihb=None):
    master = PersonnelMaster("1028", "x", "01", "01", date(1983, 7, 24))
    provider = FakeProvider(
        master, leave_groups=[], hcm213={}, excluded=excluded,
        excsenlv=excsenlv, ihb=ihb or [],
    )
    return LeaveCalculator(provider, as_of=date(2026, 6, 26))


def test_param_disabled_returns_zero():
    calc = _calc(False, {1: [LeaveRecord(date(2025, 6, 1), date(2025, 6, 30), 30)]})
    assert calc._calc_excluded_sen("01", "01", "1028", date(2025, 5, 2), date(2026, 6, 26)) == 0.0


def test_excludedsen_1_sums_totals():
    # Trace row1: EXCLUDEDSEN(1) toplami = 23.0
    excluded = {
        1: [
            LeaveRecord(date(2025, 6, 1), date(2025, 6, 10), 10.0),
            LeaveRecord(date(2025, 7, 1), date(2025, 7, 13), 13.0),
        ]
    }
    calc = _calc(True, excluded)
    result = calc._calc_excluded_sen("01", "01", "1028", date(2025, 5, 2), date(2026, 6, 26))
    assert result == 23.0


def test_excludedsen_2_under_cap_adds_nothing():
    # Rapor izni yasal sinirin (GETIHBDAY+42) altinda -> eklenmez
    excluded = {
        2: [LeaveRecord(date(2025, 6, 1), date(2025, 6, 16), 15.0)],
    }
    ihb = [IHBDayBracket("03", firstmonth=6, lastmonth=18, baseday=28)]
    calc = _calc(True, excluded, ihb)
    result = calc._calc_excluded_sen("01", "01", "1028", date(2024, 5, 2), date(2026, 6, 26))
    assert result == 0.0
