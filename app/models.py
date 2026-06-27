"""CANIAS HCM izin hesaplamasinda kullanilan alan (domain) modelleri.

Tum alan/tablo isimleri CANIAS trace dosyasindaki (HCMT101) gercek
isimlerle birebir eslesir; boylece SQL ve hesaplama mantigi takip
edilebilir kalir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class PersonnelMaster:
    """IASHCMPER + IASADRBOOKCONTACT + IASADRBKCNTORG birlesimi.

    SETREMLVDAYS parametreleri:
        COM         -> company
        PLA         -> plant
        PBIRTHDATE  -> birthday
    """

    persid: str
    contactnum: str
    company: str
    plant: str
    birthday: Optional[date]
    display: str = ""


@dataclass
class LeaveGroupRow:
    """IASHCMLVGRP satiri (personelin bir izin grubu kaydi).

    Ana SELECT (HCMT101D001.GETREMAININGDAYS.0 28) ile cekilir.
    """

    leavecode: str          # IASHCMLVGRP.LEAVECODE  (ornek: '0005')
    leavegrp: str           # IASHCMLVGRP.LEAVEGRP   (ornek: 'GR01')
    leavesendate: date      # IASHCMLVGRP.LEAVESENDATE (kidem baslangici)
    usedday: float          # IASHCMLVGRP.USEDDAY    (devreden/kullanilan)
    extrayear: int          # IASHCMLVGRP.EXTRAYEAR
    stext: str              # IASHCM306X.STEXT       (izin adi, dile gore)

    # Hesaplama sirasinda doldurulan (APPEND COLUMN) alanlar
    senyear: int = 0
    totearned: float = 0.0
    lvdays: float = 0.0
    remlvdays: float = 0.0
    excsenday: float = 0.0


@dataclass
class HCM213Bracket:
    """IASHCM213D detay satiri (kidem yilina gore izin gunu dilimi)."""

    ordnum: int
    firstyear: int
    lastyear: int
    lvdays: float


@dataclass
class HCM213Settings:
    """IASHCM213 izin grubu basligi + IASHCM213D detaylari.

    SWITCH (IASHCM213_LVGRPTYPE):
        0 -> sabit izin (GETCONSTEARNEDLVDAYS)
        1 -> degisken/yil bazli izin (GETVAREARNEDLVDAYS), ornek: yillik izin
    """

    lvgroupid: str
    lvgrptype: int            # 0=sabit, 1=degisken
    daytransfer: bool         # IASHCM213.DAYTRANSFER
    isdatebased: bool         # IASHCM213.ISDATEBASED
    lvdays: float             # IASHCM213.LVDAYS (sabit izin gun sayisi)
    monthdays: float = 0.0    # IASHCM213.MONTHDAYS
    firstlvmonth: int = 0     # IASHCM213.FIRSTLVMONTH
    stext: str = ""
    brackets: list[HCM213Bracket] = field(default_factory=list)


@dataclass
class LeaveRecord:
    """IASHCMLEAVES satiri (gerceklesmis izin kaydi)."""

    firstdate: date
    lastdate: date
    totleaveday: float
    excludedsen: int = 0     # IASHCM306.EXCLUDEDSEN (0/1/2)


@dataclass
class IHBDayBracket:
    """IASHCM321 satiri (kidem ayina gore is goremezlik baz gun sayisi)."""

    code: str
    firstmonth: int
    lastmonth: int
    baseday: int
    unionday: int = 0


@dataclass
class RemainingLeave:
    """API cikti satiri: bir izin turu icin kalan gun."""

    index: int               # REM1, REM2, ... sirasi (CNT)
    leavecode: str
    leavegrp: str
    name: str                # IASHCM306X.STEXT
    remaining_days: float    # REMLVDAYS
    earned_days: float       # TOTEARNED
    used_in_period: float    # LVDAYS
    carried_used: float      # USEDDAY
    seniority_years: int     # SENYEAR
