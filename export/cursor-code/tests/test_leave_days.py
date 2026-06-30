"""HCMT34 TOTLEAVEDAY hesaplama testleri (trace PERSID 1028, Mayis 2026)."""
from __future__ import annotations

from datetime import date, time

import pytest

from app.canias_leave_days import LeaveDayCalculator, current_month_period
from app.models import (
    HolidayPeriod,
    LeaveTypeSettings,
    RawPersonnelLeave,
    ShiftAssignment,
    ShiftDefinition,
)


class FakeLeaveDayProvider:
    def __init__(self):
        self.leave_types = {
            "0003": LeaveTypeSettings(
                leavecode="0003",
                is_monday=True,
                is_tuesday=True,
                is_wednesday=True,
                is_thursday=True,
                is_friday=True,
                is_saturday=True,
                is_sunday=False,
                is_holiday=False,
            ),
            "0013": LeaveTypeSettings(
                leavecode="0013",
                maxday=90.0,
                is_monday=True,
                is_tuesday=True,
                is_wednesday=True,
                is_thursday=True,
                is_friday=True,
                is_saturday=True,
                is_sunday=True,
                is_holiday=True,
            ),
        }
        self.shift_assignments = [
            ShiftAssignment(
                validfrom=date(2025, 5, 2),
                validuntil=date(2100, 1, 1),
                shiftnum="1",
                work_hours={day: 7.5 for day in range(1, 8)},
            )
        ]
        self.shift_def = ShiftDefinition(
            shiftcode="1",
            firsthour=time(6, 30),
            lasthour=time(14, 30),
            default_workhour=7.5,
        )
        self.holidays = [
            HolidayPeriod(start=date(2026, 5, 19), end=date(2026, 5, 19)),
        ]

    def get_leave_type_settings(self, company: str, leavecode: str):
        return self.leave_types.get(leavecode)

    def get_shift_assignments(self, persid: str):
        return self.shift_assignments

    def get_shift_definition(self, company: str, plant: str, shiftcode: str):
        return self.shift_def

    def get_holidays(self, company: str, calendar: str, year: int):
        return self.holidays if year == 2026 else []


@pytest.fixture
def calculator() -> LeaveDayCalculator:
    return LeaveDayCalculator(FakeLeaveDayProvider())


def test_current_month_period_june_2026():
    start, end = current_month_period(date(2026, 6, 15))
    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 30)


def test_trace_single_day_leave_0003(calculator: LeaveDayCalculator):
    leave = RawPersonnelLeave(
        leavenum=50,
        leavecode="0003",
        leavecode_text="Diger Ucretsiz Izin",
        confirmstat=1,
        lvstat=1,
        company="01",
        plant="01",
        firstdate=date(2026, 5, 4),
        lastdate=date(2026, 5, 4),
        firsttime=time(6, 30),
        lasttime=time(14, 30),
    )
    total = calculator.calc_totleaveday(
        leave,
        persid="1028",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        calendar="01",
    )
    assert total == 1.0


def test_trace_multi_day_leave_0013(calculator: LeaveDayCalculator):
    leave = RawPersonnelLeave(
        leavenum=49,
        leavecode="0013",
        leavecode_text="Istirahatli",
        confirmstat=1,
        lvstat=1,
        company="01",
        plant="01",
        firstdate=date(2026, 5, 11),
        lastdate=date(2026, 5, 25),
        firsttime=time(6, 30),
        lasttime=time(14, 30),
    )
    total = calculator.calc_totleaveday(
        leave,
        persid="1028",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        calendar="01",
    )
    assert total == 15.0


def test_cancelled_leave_returns_zero(calculator: LeaveDayCalculator):
    leave = RawPersonnelLeave(
        leavenum=1,
        leavecode="0003",
        leavecode_text="Diger Ucretsiz Izin",
        confirmstat=1,
        lvstat=2,
        company="01",
        plant="01",
        firstdate=date(2026, 5, 4),
        lastdate=date(2026, 5, 4),
        firsttime=time(6, 30),
        lasttime=time(14, 30),
    )
    total = calculator.calc_totleaveday(
        leave,
        persid="1028",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        calendar="01",
    )
    assert total == 0.0
