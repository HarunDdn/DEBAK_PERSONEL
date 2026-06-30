"""CANIAS HCM izin hesaplamasinda kullanilan alan (domain) modelleri.

Tum alan/tablo isimleri CANIAS trace dosyasindaki (HCMT101) gercek
isimlerle birebir eslesir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Optional


@dataclass
class PersonnelMaster:
    """IASHCMPER + IASADRBOOKCONTACT + IASADRBKCNTORG birlesimi."""

    persid: str
    contactnum: str
    company: str
    plant: str
    birthday: Optional[date]
    display: str = ""
    calendar: str = "01"


@dataclass
class LeaveTypeSettings:
    """IASHCM306 izin tipi gun kurallari (HCMT34 CALCDAYTIME)."""

    leavecode: str
    maxday: float = 0.0
    is_monday: bool = True
    is_tuesday: bool = True
    is_wednesday: bool = True
    is_thursday: bool = True
    is_friday: bool = True
    is_saturday: bool = False
    is_sunday: bool = False
    is_holiday: bool = False
    use_lvshift: bool = False


@dataclass
class ShiftAssignment:
    """IASHCMSHIFT personel vardiya atamasi."""

    validfrom: date
    validuntil: date
    shiftnum: str
    work_hours: dict[int, float] = field(default_factory=dict)


@dataclass
class ShiftDefinition:
    """IASHCM206 + IASHCM206D vardiya tanimi."""

    shiftcode: str
    firsthour: time
    lasthour: time
    endnextday: bool = False
    default_workhour: float = 7.5


@dataclass
class HolidayPeriod:
    """IASHOLIDAY tatil araligi."""

    start: date
    end: date
    is_holiday: bool = True


@dataclass
class RawPersonnelLeave:
    """IASHCMLEAVES ham kaydi (hesaplama oncesi)."""

    leavenum: int
    leavecode: str
    leavecode_text: str
    confirmstat: int
    lvstat: int
    company: str
    plant: str
    firstdate: date
    lastdate: date
    firsttime: Optional[time]
    lasttime: Optional[time]
    saveworkstyle: int = 0


@dataclass
class LeaveGroupRow:
    """IASHCMLVGRP satiri (personelin bir izin grubu kaydi)."""

    leavecode: str
    leavegrp: str
    leavesendate: date
    usedday: float
    extrayear: int
    stext: str

    senyear: int = 0
    totearned: float = 0.0
    lvdays: float = 0.0
    remlvdays: float = 0.0
    excsenday: float = 0.0


@dataclass
class HCM213Bracket:
    """IASHCM213D detay satiri."""

    ordnum: int
    firstyear: int
    lastyear: int
    lvdays: float


@dataclass
class HCM213Settings:
    """IASHCM213 izin grubu basligi + IASHCM213D detaylari."""

    lvgroupid: str
    lvgrptype: int
    daytransfer: bool
    isdatebased: bool
    lvdays: float
    monthdays: float = 0.0
    firstlvmonth: int = 0
    stext: str = ""
    brackets: list[HCM213Bracket] = field(default_factory=list)


@dataclass
class LeaveRecord:
    """IASHCMLEAVES satiri."""

    firstdate: date
    lastdate: date
    totleaveday: float
    excludedsen: int = 0


@dataclass
class IHBDayBracket:
    """IASHCM321 satiri."""

    code: str
    firstmonth: int
    lastmonth: int
    baseday: int
    unionday: int = 0


@dataclass
class PersonnelLeaveRow:
    """HCMT34 / IASHCMLEAVES izin listesi satiri."""

    leavenum: int
    leavecode: str
    leavecode_text: str
    confirmstat: int
    lvstat: int
    firstdatex: str
    firsttime: str
    lastdatex: str
    lasttime: str
    totleaveday: float


@dataclass
class RemainingLeave:
    """Hesaplama cikti satiri."""

    index: int
    leavecode: str
    leavegrp: str
    name: str
    remaining_days: float
    earned_days: float
    used_in_period: float
    carried_used: float
    seniority_years: int
