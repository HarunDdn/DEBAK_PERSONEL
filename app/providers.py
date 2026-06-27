"""Veri erisim katmani.

`LeaveDataProvider` protokolu, hesaplama motorunun (canias_leave.py)
ihtiyac duydugu tum veritabani sorgularini soyutlar. Boylece:
  - `SqlLeaveDataProvider` gercek CANIAS MSSQL veritabanina baglanir.
  - Testlerde sahte (in-memory) saglayicilar kullanilabilir.

Tum SQL'ler trace dosyasindaki orijinal sorgularin birebir karsiligidir.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Protocol

from .models import (
    HCM213Bracket,
    HCM213Settings,
    IHBDayBracket,
    LeaveGroupRow,
    LeaveRecord,
    PersonnelMaster,
)


class LeaveDataProvider(Protocol):
    """Hesaplama motorunun ihtiyac duydugu veri erisim arayuzu."""

    def get_personnel_master(self, persid: str) -> Optional[PersonnelMaster]: ...

    def get_leave_groups(self, persid: str, company: str) -> List[LeaveGroupRow]: ...

    def get_hcm213(self, company: str, lvgroupid: str) -> Optional[HCM213Settings]: ...

    def get_leaves_for_lvcode(
        self, persid: str, lvcode: str, maxdate: date, psendate: date
    ) -> List[LeaveRecord]: ...

    def get_excluded_leaves(
        self, persid: str, lvdate: date, lvsendt: date, excludedsen: int
    ) -> List[LeaveRecord]: ...

    def has_excsenlv_param(self, company: str, lvdate: date) -> bool: ...

    def get_ihbday_brackets(self, company: str) -> List[IHBDayBracket]: ...


class SqlLeaveDataProvider:
    """CANIAS Microsoft SQL Server veritabanina baglanan saglayici.

    `client` ve `langu` degerleri CANIAS oturum sabitleridir (SYS_CLIENT,
    SYS_LANGU). Trace ortaminda: CLIENT='00', LANGU='T'.
    """

    def __init__(self, connection, client: str = "00", langu: str = "T"):
        self._conn = connection
        self.client = client
        self.langu = langu

    # ------------------------------------------------------------------
    # Personel ana verisi
    # ------------------------------------------------------------------
    def get_personnel_master(self, persid: str) -> Optional[PersonnelMaster]:
        """IASHCMPER + IASADRBOOKCONTACT (dogum tarihi) + IASADRBKCNTORG (sirket/tesis).

        Org atamasi gunumuze gore gecerli olan satirdan alinir
        (VALIDFROM <= bugun <= VALIDUNTIL).
        """
        sql = """
            SELECT TOP 1
                PER.PERSID,
                PER.CONTACTNUM,
                ORG.COMPANY,
                ORG.PLANT,
                CON.BIRTHDAY,
                CON.DISPLAY
            FROM IASHCMPER PER
            INNER JOIN IASADRBOOKCONTACT CON
                ON CON.CLIENT = PER.CLIENT
               AND CON.CONTACTNUM = PER.CONTACTNUM
               AND CON.CTYPE = 1
            INNER JOIN IASADRBKCNTORG ORG
                ON ORG.CLIENT = PER.CLIENT
               AND ORG.CONTACTNUM = PER.CONTACTNUM
            WHERE PER.CLIENT = ?
              AND PER.PERSID = ?
              AND ORG.VALIDFROM <= ?
              AND ORG.VALIDUNTIL >= ?
            ORDER BY ORG.VALIDFROM DESC
        """
        today = date.today()
        cur = self._conn.cursor()
        cur.execute(sql, (self.client, persid, today, today))
        row = cur.fetchone()
        if row is None:
            return None
        return PersonnelMaster(
            persid=str(row[0]).strip(),
            contactnum=str(row[1]).strip(),
            company=str(row[2]).strip(),
            plant=str(row[3]).strip(),
            birthday=_as_date(row[4]),
            display=str(row[5] or "").strip(),
        )

    # ------------------------------------------------------------------
    # Personelin izin gruplari (ANA SORGU)
    # ------------------------------------------------------------------
    def get_leave_groups(self, persid: str, company: str) -> List[LeaveGroupRow]:
        """HCMT101D001.GETREMAININGDAYS.0 28 sorgusunun birebir kopyasi."""
        sql = """
            SELECT
                IASHCMLVGRP.LEAVECODE,
                IASHCMLVGRP.LEAVEGRP,
                IASHCMLVGRP.LEAVESENDATE,
                IASHCMLVGRP.USEDDAY,
                IASHCMLVGRP.EXTRAYEAR,
                IASHCM306X.STEXT AS STEXT
            FROM IASHCMLVGRP
            LEFT JOIN IASHCM306
                ON (IASHCMLVGRP.CLIENT = IASHCM306.CLIENT
                AND IASHCMLVGRP.LEAVECODE = IASHCM306.LEAVECODE)
            LEFT JOIN IASHCM306X
                ON (IASHCM306.CLIENT = IASHCM306X.CLIENT
                AND IASHCM306.COMPANY = IASHCM306X.COMPANY
                AND IASHCM306.LEAVECODE = IASHCM306X.LEAVECODE)
            WHERE IASHCMLVGRP.CLIENT = ?
              AND IASHCMLVGRP.PERSID = ?
              AND IASHCM306.COMPANY = ?
              AND IASHCM306X.LANGU = ?
            ORDER BY IASHCM306.LEAVECODE
        """
        cur = self._conn.cursor()
        cur.execute(sql, (self.client, persid, company, self.langu))
        rows: List[LeaveGroupRow] = []
        for r in cur.fetchall():
            rows.append(
                LeaveGroupRow(
                    leavecode=str(r[0]).strip(),
                    leavegrp=str(r[1]).strip(),
                    leavesendate=_as_date(r[2]),
                    usedday=_as_float(r[3]),
                    extrayear=int(_as_float(r[4])),
                    stext=str(r[5] or "").strip(),
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Izin grubu ayarlari (IASHCM213 + IASHCM213D)
    # ------------------------------------------------------------------
    def get_hcm213(self, company: str, lvgroupid: str) -> Optional[HCM213Settings]:
        """HCM213REC.FETCH: IASHCM213 basligi + IASHCM213D detaylari."""
        head_sql = """
            SELECT
                IASHCM213.LVGROUPID,
                IASHCM213.LVGRPTYPE,
                IASHCM213.DAYTRANSFER,
                IASHCM213.ISDATEBASED,
                IASHCM213.LVDAYS,
                IASHCM213.MONTHDAYS,
                IASHCM213.FIRSTLVMONTH,
                IASHCM213X.STEXT
            FROM IASHCM213
            LEFT JOIN IASHCM213X
                ON IASHCM213X.CLIENT = IASHCM213.CLIENT
               AND IASHCM213X.COMPANY = IASHCM213.COMPANY
               AND IASHCM213X.LVGROUPID = IASHCM213.LVGROUPID
               AND IASHCM213X.LANGU = ?
            WHERE IASHCM213.CLIENT = ?
              AND IASHCM213.COMPANY = ?
              AND IASHCM213.LVGROUPID = ?
        """
        cur = self._conn.cursor()
        cur.execute(head_sql, (self.langu, self.client, company, lvgroupid))
        h = cur.fetchone()
        if h is None:
            return None

        det_sql = """
            SELECT ORDNUM, FIRSTYEAR, LASTYEAR, LVDAYS
            FROM IASHCM213D
            WHERE CLIENT = ?
              AND COMPANY = ?
              AND LVGROUPID = ?
            ORDER BY ORDNUM
        """
        cur.execute(det_sql, (self.client, company, lvgroupid))
        brackets = [
            HCM213Bracket(
                ordnum=int(_as_float(d[0])),
                firstyear=int(_as_float(d[1])),
                lastyear=int(_as_float(d[2])),
                lvdays=_as_float(d[3]),
            )
            for d in cur.fetchall()
        ]

        return HCM213Settings(
            lvgroupid=str(h[0]).strip(),
            lvgrptype=int(_as_float(h[1])),
            daytransfer=_as_bool(h[2]),
            isdatebased=_as_bool(h[3]),
            lvdays=_as_float(h[4]),
            monthdays=_as_float(h[5]),
            firstlvmonth=int(_as_float(h[6])),
            stext=str(h[7] or "").strip(),
            brackets=brackets,
        )

    # ------------------------------------------------------------------
    # Kullanilan izinler (GETLEAVEDAYS)
    # ------------------------------------------------------------------
    def get_leaves_for_lvcode(
        self, persid: str, lvcode: str, maxdate: date, psendate: date
    ) -> List[LeaveRecord]:
        """HCMLEAVEREC.GETLEAVEDAYS.0 29 sorgusu."""
        sql = """
            SELECT FIRSTDATE, LASTDATE, TOTLEAVEDAY
            FROM IASHCMLEAVES
            WHERE CLIENT = ?
              AND PERSID = ?
              AND LEAVECODE = ?
              AND FIRSTDATE <= ?
              AND (LASTDATE > ? OR (FIRSTDATE = ? AND LASTDATE = ?))
            ORDER BY FIRSTDATE
        """
        cur = self._conn.cursor()
        cur.execute(sql, (self.client, persid, lvcode, maxdate, psendate, psendate, psendate))
        return [
            LeaveRecord(
                firstdate=_as_date(r[0]),
                lastdate=_as_date(r[1]),
                totleaveday=_as_float(r[2]),
            )
            for r in cur.fetchall()
        ]

    # ------------------------------------------------------------------
    # Kidem disi (excluded) izinler (CALCEXCLUDEDSEN)
    # ------------------------------------------------------------------
    def get_excluded_leaves(
        self, persid: str, lvdate: date, lvsendt: date, excludedsen: int
    ) -> List[LeaveRecord]:
        """CALCEXCLUDEDSEN.0 34/49 sorgulari (EXCLUDEDSEN = 1 veya 2)."""
        sql = """
            SELECT LV.FIRSTDATE, LV.LASTDATE, LV.TOTLEAVEDAY
            FROM IASHCMLEAVES LV
            INNER JOIN IASHCM306 H306
                ON H306.CLIENT = LV.CLIENT
               AND H306.COMPANY = LV.COMPANY
               AND H306.LEAVECODE = LV.LEAVECODE
               AND H306.EXCLUDEDSEN = ?
            WHERE LV.CLIENT = ?
              AND LV.PERSID = ?
              AND LV.FIRSTDATE <= ?
              AND LV.LASTDATE >= ?
              AND LV.CONFIRMSTAT <= 1
              AND LV.LVSTAT <= 1
            ORDER BY LV.FIRSTDATE
        """
        cur = self._conn.cursor()
        cur.execute(sql, (excludedsen, self.client, persid, lvdate, lvsendt))
        return [
            LeaveRecord(
                firstdate=_as_date(r[0]),
                lastdate=_as_date(r[1]),
                totleaveday=_as_float(r[2]),
                excludedsen=excludedsen,
            )
            for r in cur.fetchall()
        ]

    def has_excsenlv_param(self, company: str, lvdate: date) -> bool:
        """HCM302REC.GETONEPARAMVAL: EXCSENLV parametresi tanimli/acik mi?"""
        sql = """
            SELECT PARAMETERTEXT
            FROM IASHCM302V
            WHERE CLIENT = ?
              AND COMPANY = ?
              AND PARAMETERID = 'EXCSENLV'
              AND VALIDFROM <= ?
              AND VALIDUNTIL >= ?
        """
        cur = self._conn.cursor()
        cur.execute(sql, (self.client, company, lvdate, lvdate))
        row = cur.fetchone()
        if row is None:
            return False
        return _as_bool(row[0])

    def get_ihbday_brackets(self, company: str) -> List[IHBDayBracket]:
        """HCMSVRNREC.GETIHBDAY: IASHCM321 is goremezlik baz gun tablosu."""
        sql = """
            SELECT CODE, FIRSTMONTH, LASTMONTH, BASEDAY, UNIONDAY
            FROM IASHCM321
            WHERE CLIENT = ?
              AND COMPANY = ?
            ORDER BY CODE
        """
        cur = self._conn.cursor()
        try:
            cur.execute(sql, (self.client, company))
        except Exception:
            # UNIONDAY kolonu yoksa sendikasiz baz gun ile devam et
            cur.execute(
                "SELECT CODE, FIRSTMONTH, LASTMONTH, BASEDAY, 0 FROM IASHCM321 "
                "WHERE CLIENT = ? AND COMPANY = ? ORDER BY CODE",
                (self.client, company),
            )
        return [
            IHBDayBracket(
                code=str(r[0]).strip(),
                firstmonth=int(_as_float(r[1])),
                lastmonth=int(_as_float(r[2])),
                baseday=int(_as_float(r[3])),
                unionday=int(_as_float(r[4])),
            )
            for r in cur.fetchall()
        ]


# ----------------------------------------------------------------------
# Yardimci tip donusturucular
# ----------------------------------------------------------------------
def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return value


def _as_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() in ("1", "True", "true", "X", "x", "Y")
    return bool(_as_float(value))
