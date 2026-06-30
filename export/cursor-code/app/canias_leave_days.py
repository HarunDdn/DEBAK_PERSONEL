"""HCMT34 TOTLEAVEDAY hesaplama motoru (HCMLEAVEREC.CALCLEAVEDAYTIME).

Trace fonksiyonlari:
    HCMLEAVEREC.CALCLEAVEDAYTIME  -> LeaveDayCalculator.calc_leave_daytime
    HCMLEAVEREC.CALCDAYTIME       -> LeaveDayCalculator._calc_daytime
    HCMLEAVEREC.GETONEDAYCOUNT    -> LeaveDayCalculator._get_one_day_count
    HCMLEAVEREC.CHECKSTATUS       -> LeaveDayCalculator._check_status
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import List, Optional, Protocol

from . import calendar_utils as cal
from .models import HolidayPeriod, LeaveTypeSettings, RawPersonnelLeave, ShiftAssignment, ShiftDefinition


class LeaveDayDataProvider(Protocol):
    def get_leave_type_settings(self, company: str, leavecode: str) -> Optional[LeaveTypeSettings]: ...

    def get_shift_assignments(self, persid: str) -> List[ShiftAssignment]: ...

    def get_shift_definition(
        self, company: str, plant: str, shiftcode: str
    ) -> Optional[ShiftDefinition]: ...

    def get_holidays(self, company: str, calendar: str, year: int) -> List[HolidayPeriod]: ...


@dataclass
class ClippedLeave:
    firstdate: date
    lastdate: date
    firsttime: Optional[time]
    lasttime: Optional[time]


class LeaveDayCalculator:
    """CANIAS HCMT34 izin gunu hesaplayicisi."""

    def __init__(self, provider: LeaveDayDataProvider):
        self.provider = provider
        self._shift_cache: dict[tuple[str, str, str], ShiftDefinition] = {}
        self._holiday_cache: dict[tuple[str, str, int], List[HolidayPeriod]] = {}

    def calc_totleaveday(
        self,
        leave: RawPersonnelLeave,
        *,
        persid: str,
        period_start: date,
        period_end: date,
        calendar: str,
    ) -> float:
        if not self._check_status(leave.confirmstat, leave.lvstat):
            return 0.0

        clipped = self._clip_to_period(leave, period_start, period_end)
        if clipped.firstdate > clipped.lastdate:
            return 0.0

        settings = self.provider.get_leave_type_settings(leave.company, leave.leavecode)
        if settings is None:
            return 0.0

        total = 0.0
        current = clipped.firstdate
        while current <= clipped.lastdate:
            day_count = self._calc_daytime(
                company=leave.company,
                plant=leave.plant,
                persid=persid,
                work_date=current,
                leave=leave,
                clipped=clipped,
                settings=settings,
                calendar=calendar,
            )
            total += day_count
            if settings.maxday > 0 and total >= settings.maxday:
                total = settings.maxday
                break
            current += timedelta(days=1)

        return round(total, 2)

    def _clip_to_period(
        self, leave: RawPersonnelLeave, period_start: date, period_end: date
    ) -> ClippedLeave:
        firstdate = leave.firstdate
        lastdate = leave.lastdate
        firsttime = leave.firsttime
        lasttime = leave.lasttime

        if firstdate < period_start:
            firstdate = period_start
            firsttime = None
        if lastdate > period_end:
            lastdate = period_end
            lasttime = None

        return ClippedLeave(
            firstdate=firstdate,
            lastdate=lastdate,
            firsttime=firsttime,
            lasttime=lasttime,
        )

    @staticmethod
    def _check_status(confirmstat: int, lvstat: int) -> bool:
        # CHECKSTATUS: onaylanmamis veya iptal edilmis kayitlar hesaba katilmaz.
        if confirmstat > 1:
            return False
        if lvstat == 2:
            return False
        return True

    def _calc_daytime(
        self,
        *,
        company: str,
        plant: str,
        persid: str,
        work_date: date,
        leave: RawPersonnelLeave,
        clipped: ClippedLeave,
        settings: LeaveTypeSettings,
        calendar: str,
    ) -> float:
        assignment = self._locate_shift(persid, work_date)
        if assignment is None:
            return 0.0

        shift = self._get_shift_definition(company, plant, assignment.shiftnum)
        if shift is None:
            return 0.0

        daynum = self._canias_day_of_week(work_date)
        daily_workhour = assignment.work_hours.get(daynum, shift.default_workhour)

        holidays = self._get_holidays(company, calendar, work_date.year)
        is_holiday = self._is_holiday(work_date, holidays)

        if is_holiday:
            if settings.is_holiday:
                return 1.0
            return 0.0

        lv_first_time = clipped.firsttime if work_date == clipped.firstdate else None
        lv_last_time = clipped.lasttime if work_date == clipped.lastdate else None

        if lv_first_time is None and lv_last_time is None:
            one_day_count = 1.0
        else:
            first_t = lv_first_time or shift.firsthour
            last_t = lv_last_time or shift.lasthour
            one_day_count = self._get_one_day_count(shift, first_t, last_t)

        if not self._day_allowed(daynum, settings):
            return 0.0

        return round(one_day_count, 4)

    def _get_one_day_count(
        self, shift: ShiftDefinition, first_time: time, last_time: time
    ) -> float:
        full_minutes = _minute_diff(shift.firsthour, shift.lasthour)
        if full_minutes <= 0:
            return 0.0
        one_minutes = abs(_minute_diff(first_time, last_time))
        one_hour = round(one_minutes / 60.0, 2)
        full_hour = round(full_minutes / 60.0, 2)
        if full_hour <= 0:
            return 0.0
        return round(one_hour / full_hour, 4)

    def _locate_shift(self, persid: str, work_date: date) -> Optional[ShiftAssignment]:
        for row in self.provider.get_shift_assignments(persid):
            if row.validfrom <= work_date <= row.validuntil:
                return row
        return None

    def _get_shift_definition(
        self, company: str, plant: str, shiftcode: str
    ) -> Optional[ShiftDefinition]:
        key = (company, plant, shiftcode)
        if key not in self._shift_cache:
            self._shift_cache[key] = self.provider.get_shift_definition(company, plant, shiftcode)
        return self._shift_cache[key]

    def _get_holidays(self, company: str, calendar: str, year: int) -> List[HolidayPeriod]:
        key = (company, calendar, year)
        if key not in self._holiday_cache:
            self._holiday_cache[key] = self.provider.get_holidays(company, calendar, year)
        return self._holiday_cache[key]

    @staticmethod
    def _is_holiday(work_date: date, holidays: List[HolidayPeriod]) -> bool:
        for h in holidays:
            if h.start <= work_date <= h.end:
                return True
        return False

    @staticmethod
    def _canias_day_of_week(work_date: date) -> int:
        # CANIAS GETDAYOFWEEK: Pazartesi=1 ... Pazar=7
        return work_date.weekday() + 1

    @staticmethod
    def _day_allowed(daynum: int, settings: LeaveTypeSettings) -> bool:
        flags = {
            1: settings.is_monday,
            2: settings.is_tuesday,
            3: settings.is_wednesday,
            4: settings.is_thursday,
            5: settings.is_friday,
            6: settings.is_saturday,
            7: settings.is_sunday,
        }
        return flags.get(daynum, False)


def _minute_diff(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def current_month_period(as_of: Optional[date] = None) -> tuple[date, date]:
    """Icinde bulunulan ayin ilk ve son gunu."""
    ref = as_of or date.today()
    start = date(ref.year, ref.month, 1)
    if ref.month == 12:
        end = date(ref.year, 12, 31)
    else:
        end = date(ref.year, ref.month + 1, 1) - timedelta(days=1)
    return start, end
