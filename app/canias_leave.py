"""CANIAS HCM kalan izin (REMLVDAYS) hesaplama motoru.

Bu modul, CANIAS trace dosyasindaki (HCMT101) sunucu tarafi mantigin
Python karsiligidir. Asagidaki TROIA fonksiyonlari birebir taklit edilir:

    HCMT101D001.GETREMAININGDAYS  ->  LeaveCalculator.get_remaining_days
    HCMLEAVEREC.SETREMLVDAYS      ->  LeaveCalculator._set_rem_lvdays
    HCMLEAVEREC.CALCEXCLUDEDSEN   ->  LeaveCalculator._calc_excluded_sen
    HCMLEAVEREC.GETLEAVEDAYS      ->  LeaveCalculator._get_leave_days
    HCMLEAVEREC.GETEARNEDLVDAYS   ->  LeaveCalculator._get_earned_lvdays
    HCMLEAVEREC.GETCONSTEARNEDLVDAYS / GETCONSTYEARLV
    HCMLEAVEREC.GETVAREARNEDLVDAYS / GETYEARBASEDLVDAYS / GETSENLEAVEDAYS
    HCMSVRNREC.GETIHBDAY

Temel formul (SETREMLVDAYS.0 58):
    REMLVDAYS = TOTEARNED - LVDAYS - USEDDAY
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from . import calendar_utils as cal
from .models import (
    HCM213Settings,
    LeaveGroupRow,
    PersonnelMaster,
    RemainingLeave,
)
from .providers import LeaveDataProvider

# CANIAS'ta GETLEAVEDAYS'e gecilen ust tarih siniri (MAXDATE). Trace: 01.01.2100
MAXDATE = date(2100, 1, 1)


class PersonnelNotFound(Exception):
    """Verilen PERSID icin personel ana verisi bulunamadi."""


class LeaveCalculator:
    """Bir personelin kalan izin gunlerini CANIAS mantigiyla hesaplar."""

    def __init__(
        self,
        provider: LeaveDataProvider,
        *,
        default_company: str = "01",
        default_plant: str = "01",
        sendika: int = 0,
        as_of: Optional[date] = None,
    ):
        self.provider = provider
        self.default_company = default_company
        self.default_plant = default_plant
        self.sendika = sendika
        # PLVDATE = SYS_CURRENTDATE (trace'te TDY). Test edilebilirlik icin override.
        self.lvdate = as_of or date.today()

    # ------------------------------------------------------------------
    # HCMT101D001.GETREMAININGDAYS
    # ------------------------------------------------------------------
    def get_remaining_days(self, persid: str) -> List[RemainingLeave]:
        """Personelin tum izin gruplari icin kalan gunleri dondurur.

        Donen liste sirasi CANIAS'taki REM1, REM2, ... alanlariyla aynidir
        (ANA SORGU `ORDER BY IASHCM306.LEAVECODE`).
        """
        master = self.provider.get_personnel_master(persid)
        if master is None:
            # Personel ana verisi yoksa varsayilan sirket/tesis ile devam et,
            # ancak dogum tarihi olmadan yil-bazli izinler hesaplanamaz.
            raise PersonnelNotFound(f"PERSID bulunamadi: {persid}")

        company = master.company or self.default_company
        plant = master.plant or self.default_plant

        rows = self.provider.get_leave_groups(persid, company)

        results: List[RemainingLeave] = []
        cnt = 0
        for row in rows:
            self._set_rem_lvdays(
                row,
                company=company,
                plant=plant,
                persid=persid,
                birthday=master.birthday,
            )
            cnt += 1
            results.append(
                RemainingLeave(
                    index=cnt,
                    leavecode=row.leavecode,
                    leavegrp=row.leavegrp,
                    name=row.stext,
                    remaining_days=round(row.remlvdays, 2),
                    earned_days=round(row.totearned, 2),
                    used_in_period=round(row.lvdays, 2),
                    carried_used=round(row.usedday, 2),
                    seniority_years=row.senyear,
                )
            )
        return results

    # ------------------------------------------------------------------
    # HCMLEAVEREC.SETREMLVDAYS  (her izin grubu satiri icin)
    # ------------------------------------------------------------------
    def _set_rem_lvdays(
        self,
        row: LeaveGroupRow,
        *,
        company: str,
        plant: str,
        persid: str,
        birthday: Optional[date],
    ) -> None:
        plvcode = row.leavecode
        plvgrp = row.leavegrp
        psendate = row.leavesendate
        row.totearned = 0.0
        row.remlvdays = 0.0

        # SETREMLVDAYS.0 34: izin grubu ayari yoksa satir atlanir (REMLVDAYS = 0)
        hcm213 = self.provider.get_hcm213(company, plvgrp)
        if hcm213 is None:
            return

        # SETREMLVDAYS.0 38: kidem disi (excluded) gun sayisi
        excludedsen = self._calc_excluded_sen(
            company, plant, persid, psendate, self.lvdate
        )
        if excludedsen > 0:
            psendate = cal.add_days(psendate, excludedsen)  # .0 40
            row.excsenday = excludedsen

        # SETREMLVDAYS.0 44-46: kidem yili
        senyear = cal.get_year_diff(psendate, self.lvdate)
        senyear = senyear + row.extrayear
        psendate = cal.sub_years(psendate, row.extrayear)
        row.senyear = senyear

        # SETREMLVDAYS.0 48: gun devri yoksa kidem baslangici donem basina cekilir
        if not hcm213.daytransfer:
            psendate = cal.add_years(psendate, senyear)
            if psendate > self.lvdate:
                # Trace'te tetiklenmedi; donem henuz dolmadiysa bir yil geri al
                psendate = cal.sub_years(psendate, 1)

        # SETREMLVDAYS.0 56: ilgili donemde kullanilan izin
        row.lvdays = self._get_leave_days(persid, plvcode, MAXDATE, psendate)

        # SETREMLVDAYS.0 57: kazanilan toplam izin
        row.totearned = self._get_earned_lvdays(
            hcm213, self.lvdate, psendate, birthday, senyear
        )

        # SETREMLVDAYS.0 58: kalan izin
        row.remlvdays = row.totearned - row.lvdays - row.usedday

    # ------------------------------------------------------------------
    # HCMLEAVEREC.GETLEAVEDAYS
    # ------------------------------------------------------------------
    def _get_leave_days(
        self, persid: str, lvcode: str, maxdate: date, psendate: date
    ) -> float:
        """Donem icinde kullanilan toplam izin gununu dondurur (TOTLEAVEDAY toplami).

        Trace: GETLEAVEDAYS'e PLVDATE olarak MAXDATE (01.01.2100) gecilir; bu
        nedenle `LASTDATE > PLVDATE` kontrolu pratikte hep yanlistir ve donen
        tum satirlar toplanir.
        """
        records = self.provider.get_leaves_for_lvcode(persid, lvcode, maxdate, psendate)
        total = 0.0
        for rec in records:
            # GETLEAVEDAYS.0 34: LASTDATE > PLVDATE(=MAXDATE) ise atla
            if rec.lastdate > maxdate:
                continue
            total += rec.totleaveday
        return total

    # ------------------------------------------------------------------
    # HCMLEAVEREC.GETEARNEDLVDAYS  (SWITCH LVGRPTYPE)
    # ------------------------------------------------------------------
    def _get_earned_lvdays(
        self,
        hcm213: HCM213Settings,
        lvdt: date,
        sendate: date,
        birthday: Optional[date],
        senyear: int,
    ) -> float:
        # GETEARNEDLVDAYS.0 14: kidem baslangici izin tarihinden sonraysa 0
        if sendate > lvdt:
            return 0.0

        if hcm213.lvgrptype == 0:
            # Sabit izin
            return self._get_const_earned_lvdays(hcm213, lvdt, sendate)
        elif hcm213.lvgrptype == 1:
            # Degisken / yil bazli izin (ornek: yillik izin)
            return self._get_var_earned_lvdays(hcm213, lvdt, sendate, birthday)
        # Bilinmeyen tip -> 0
        return 0.0

    # ------------------------------------------------------------------
    # HCMLEAVEREC.GETCONSTEARNEDLVDAYS + GETCONSTYEARLV
    # ------------------------------------------------------------------
    def _get_const_earned_lvdays(
        self, hcm213: HCM213Settings, lvdt: date, sendate: date
    ) -> float:
        # GETCONSTEARNEDLVDAYS.0 14: aylik gun tahakkuku (MONTHDAYS) - opsiyonel
        if hcm213.monthdays > 0:
            # Aydan aya tahakkuk: kidem ayi * aylik gun
            months = cal.get_year_diff(sendate, lvdt) * 12
            # (FIRSTLVMONTH offseti kurum ayarina bagli; trace'te kullanilmadi)
            return months * hcm213.monthdays

        # GETCONSTYEARLV: gun devri yoksa dogrudan IASHCM213.LVDAYS
        return self._get_const_year_lv(hcm213)

    def _get_const_year_lv(self, hcm213: HCM213Settings) -> float:
        # GETCONSTYEARLV.0 7-10
        if hcm213.daytransfer:
            # Gun devri varsa her kidem yili icin LVDAYS biriktirilir.
            # (Sabit + gun devri kombinasyonu trace'te yok; LVDAYS dondurulur.)
            return hcm213.lvdays
        return hcm213.lvdays

    # ------------------------------------------------------------------
    # HCMLEAVEREC.GETVAREARNEDLVDAYS + GETYEARBASEDLVDAYS + GETSENLEAVEDAYS
    # ------------------------------------------------------------------
    def _get_var_earned_lvdays(
        self,
        hcm213: HCM213Settings,
        lvdt: date,
        sendate: date,
        birthday: Optional[date],
    ) -> float:
        """Yil bazli kazanilan izin.

        GETVAREARNEDLVDAYS.0: kidem baslangicindan itibaren her tam yil icin,
        o kidem yilina ve yasa karsilik gelen izin gununu toplar.
        """
        yeardiff = cal.get_year_diff(sendate, lvdt)
        if yeardiff <= 0:
            return 0.0

        total = 0.0
        tmpsendate = sendate
        yearorder = 0
        # WHILE YEARORDER < YEARDIFF && YEARORDER < 100
        while yearorder < yeardiff and yearorder < 100:
            yearorder += 1
            tmpsendate = cal.add_years(tmpsendate, 1)
            persage = cal.get_year_diff(birthday, tmpsendate) if birthday else 30
            total += self._get_year_based_lvdays(hcm213, persage, yearorder)
        return total

    def _get_year_based_lvdays(
        self, hcm213: HCM213Settings, persage: int, senyear: int
    ) -> float:
        """GETYEARBASEDLVDAYS: bir kidem yili icin izin gunu.

        - Kidem dilimi (IASHCM213D) icinde FIRSTYEAR<=senyear<=LASTYEAR olan
          satirin en yuksek LVDAYS degeri esas alinir.
        - 18 yas alti veya 50 yas ve uzeri icin yasal asgari 20 gun uygulanir
          (4857 sayili Is Kanunu m.53). Trace'te bu sube tetiklenmedi.
        """
        leavedays = 0.0
        for b in hcm213.brackets:
            if b.firstyear <= senyear <= b.lastyear:
                if b.lvdays > leavedays:
                    leavedays = b.lvdays

        leavedays = self._get_sen_leave_days(hcm213, senyear, leavedays)

        # Yasal asgari: 18 alti / 50 ve uzeri -> en az 20 gun
        if persage < 18 or persage >= 50:
            if leavedays < 20:
                leavedays = 20.0
        return leavedays

    def _get_sen_leave_days(
        self, hcm213: HCM213Settings, senyear: int, minlvdays: float
    ) -> float:
        """GETSENLEAVEDAYS: dilim bazli izin gunu (tarih bazli degilse)."""
        lvdays = 0.0
        if not hcm213.isdatebased:
            for b in hcm213.brackets:
                if b.firstyear <= senyear <= b.lastyear:
                    lvdays = b.lvdays
                    break
        if lvdays < minlvdays:
            lvdays = minlvdays
        return lvdays

    # ------------------------------------------------------------------
    # HCMLEAVEREC.CALCEXCLUDEDSEN
    # ------------------------------------------------------------------
    def _calc_excluded_sen(
        self,
        company: str,
        plant: str,
        persid: str,
        lvsendt: date,
        lvdate: date,
    ) -> float:
        """Kidem disinda birakilacak gun sayisini hesaplar.

        - EXCSENLV parametresi tanimli degilse 0 dondurur (.0 21).
        - EXCLUDEDSEN=1 izinlerin tum TOTLEAVEDAY toplami kidem disidir (.0 34-37).
        - EXCLUDEDSEN=2 (is goremezlik/rapor) izinlerde sadece yasal sinirin
          (GETIHBDAY + 42) USTUNDEKI gunler kidem disi sayilir (.0 49-63).
        """
        if not self.provider.has_excsenlv_param(company, lvdate):
            return 0.0

        # EXCLUDEDSEN = 1: dogrudan toplanir
        excl1 = self.provider.get_excluded_leaves(persid, lvdate, lvsendt, 1)
        outofsenday = sum(r.totleaveday for r in excl1)

        # EXCLUDEDSEN = 2: rapor gunleri, yasal sinir asimi kadar eklenir
        excl2 = self.provider.get_excluded_leaves(persid, lvdate, lvsendt, 2)
        if excl2:
            ihb_brackets = self.provider.get_ihbday_brackets(company)
            for rec in excl2:
                kyear, kmonth, _ = cal.svrn_date_diff(lvsendt, rec.firstdate)
                month = kyear * 12 + kmonth
                maxdenunday = self._get_ihb_day(ihb_brackets, month) + 42
                if maxdenunday < rec.totleaveday:
                    outofsenday += rec.totleaveday - maxdenunday

        return outofsenday

    # ------------------------------------------------------------------
    # HCMSVRNREC.GETIHBDAY
    # ------------------------------------------------------------------
    def _get_ihb_day(self, brackets, month: float) -> int:
        """IASHCM321 dilimlerinden kidem ayina karsilik baz gun sayisi."""
        ihbday = 0
        for b in brackets:
            lmonth = b.lastmonth
            if lmonth == 0:
                continue
            if month >= b.firstmonth and month < lmonth:
                ihbday = b.unionday if self.sendika else b.baseday
                break
        return ihbday
