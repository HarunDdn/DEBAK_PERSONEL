"""Veri erisim katmani.

`LeaveDataProvider` protokolu, hesaplama motorunun (canias_leave.py)
ihtiyac duydugu tum veritabani sorgularini soyutlar. Boylece:
  - `SqlLeaveDataProvider` gercek CANIAS MSSQL veritabanina baglanir.
  - Testlerde sahte (in-memory) saglayicilar kullanilabilir.

Tum SQL'ler trace dosyasindaki orijinal sorgularin birebir karsiligidir.
"""
from __future__ import annotations

from datetime import date, datetime
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

    def __init__(
        self,
        connection,
        client: str = "00",
        langu: str = "T",
        db_schema: str | None = None,
    ):
        self._conn = connection
        self.client = client
        self.langu = langu
        self.db_schema = (db_schema or "").strip() or None
        self._table_cache: dict[str, str] = {}

    def _table(self, name: str) -> str:
        """Tablo adini dogru schema ile donur.

        Ortamda varsayilan schema `dbo` degilse veya farkli bir schema
        kullaniliyorsa `Invalid object name` hatalarini engeller.
        """
        cached = self._table_cache.get(name)
        if cached:
            return cached

        if self.db_schema:
            qualified = f"[{self.db_schema}].[{name}]"
            self._table_cache[name] = qualified
            return qualified

        cur = self._conn.cursor()
        try:
            cur.execute(
                """
                SELECT TOP 1 s.name
                FROM sys.tables t
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE t.name = ?
                ORDER BY CASE WHEN s.name = 'dbo' THEN 0 ELSE 1 END, s.name
                """,
                (name,),
            )
            row = cur.fetchone()
            if row and row[0]:
                qualified = f"[{str(row[0]).strip()}].[{name}]"
                self._table_cache[name] = qualified
                return qualified
        except Exception:
            # Meta tablolara erisim yoksa mevcut davranisa geri don.
            pass

        self._table_cache[name] = name
        return name

    # ------------------------------------------------------------------
    # Personel ana verisi
    # ------------------------------------------------------------------
    def get_personnel_master(self, persid: str) -> Optional[PersonnelMaster]:
        """IASHCMPER + IASADRBOOKCONTACT (dogum tarihi) + IASADRBKCNTORG (sirket/tesis).

        Org atamasi gunumuze gore gecerli olan satirdan alinir
        (VALIDFROM <= bugun <= VALIDUNTIL).
        """
        t_per = self._table("IASHCMPER")
        t_con = self._table("IASADRBOOKCONTACT")
        t_org = self._table("IASADRBKCNTORG")
        sql = """
            SELECT TOP 1
                PER.PERSID,
                PER.CONTACTNUM,
                ORG.COMPANY,
                ORG.PLANT,
                CON.BIRTHDAY,
                CON.DISPLAY
            FROM {t_per} PER
            INNER JOIN {t_con} CON
                ON CON.CLIENT = PER.CLIENT
               AND CON.CONTACTNUM = PER.CONTACTNUM
               AND CON.CTYPE = 1
            INNER JOIN {t_org} ORG
                ON ORG.CLIENT = PER.CLIENT
               AND ORG.CONTACTNUM = PER.CONTACTNUM
            WHERE PER.CLIENT = ?
              AND PER.PERSID = ?
              AND ORG.VALIDFROM <= ?
              AND ORG.VALIDUNTIL >= ?
            ORDER BY ORG.VALIDFROM DESC
                """.format(t_per=t_per, t_con=t_con, t_org=t_org)
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
        t_lvgrp = self._table("IASHCMLVGRP")
        t_306 = self._table("IASHCM306")
        t_306x = self._table("IASHCM306X")
        sql = """
            SELECT
                IASHCMLVGRP.LEAVECODE,
                IASHCMLVGRP.LEAVEGRP,
                IASHCMLVGRP.LEAVESENDATE,
                IASHCMLVGRP.USEDDAY,
                IASHCMLVGRP.EXTRAYEAR,
                IASHCM306X.STEXT AS STEXT
            FROM {t_lvgrp} IASHCMLVGRP
            LEFT JOIN {t_306} IASHCM306
                ON (IASHCMLVGRP.CLIENT = IASHCM306.CLIENT
                AND IASHCMLVGRP.LEAVECODE = IASHCM306.LEAVECODE)
            LEFT JOIN {t_306x} IASHCM306X
                ON (IASHCM306.CLIENT = IASHCM306X.CLIENT
                AND IASHCM306.COMPANY = IASHCM306X.COMPANY
                AND IASHCM306.LEAVECODE = IASHCM306X.LEAVECODE)
            WHERE IASHCMLVGRP.CLIENT = ?
              AND IASHCMLVGRP.PERSID = ?
              AND IASHCM306.COMPANY = ?
              AND IASHCM306X.LANGU = ?
            ORDER BY IASHCM306.LEAVECODE
                """.format(t_lvgrp=t_lvgrp, t_306=t_306, t_306x=t_306x)
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
        t_213 = self._table("IASHCM213")
        t_213x = self._table("IASHCM213X")
        t_213d = self._table("IASHCM213D")
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
            FROM {t_213} IASHCM213
            LEFT JOIN {t_213x} IASHCM213X
                ON IASHCM213X.CLIENT = IASHCM213.CLIENT
               AND IASHCM213X.COMPANY = IASHCM213.COMPANY
               AND IASHCM213X.LVGROUPID = IASHCM213.LVGROUPID
               AND IASHCM213X.LANGU = ?
            WHERE IASHCM213.CLIENT = ?
              AND IASHCM213.COMPANY = ?
              AND IASHCM213.LVGROUPID = ?
                """.format(t_213=t_213, t_213x=t_213x)
        cur = self._conn.cursor()
        cur.execute(head_sql, (self.langu, self.client, company, lvgroupid))
        h = cur.fetchone()
        if h is None:
            return None

        det_sql = """
            SELECT ORDNUM, FIRSTYEAR, LASTYEAR, LVDAYS
                        FROM {t_213d}
            WHERE CLIENT = ?
              AND COMPANY = ?
              AND LVGROUPID = ?
            ORDER BY ORDNUM
                """.format(t_213d=t_213d)
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
        t_leaves = self._table("IASHCMLEAVES")
        sql = """
            SELECT FIRSTDATE, LASTDATE, TOTLEAVEDAY
            FROM {t_leaves}
            WHERE CLIENT = ?
              AND PERSID = ?
              AND LEAVECODE = ?
              AND FIRSTDATE <= ?
              AND (LASTDATE > ? OR (FIRSTDATE = ? AND LASTDATE = ?))
            ORDER BY FIRSTDATE
        """.format(t_leaves=t_leaves)
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
        t_leaves = self._table("IASHCMLEAVES")
        t_306 = self._table("IASHCM306")
        sql = """
            SELECT LV.FIRSTDATE, LV.LASTDATE, LV.TOTLEAVEDAY
            FROM {t_leaves} LV
            INNER JOIN {t_306} H306
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
                """.format(t_leaves=t_leaves, t_306=t_306)
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
        t_302v = self._table("IASHCM302V")
        sql = """
            SELECT PARAMETERTEXT
            FROM {t_302v}
            WHERE CLIENT = ?
              AND COMPANY = ?
              AND PARAMETERID = 'EXCSENLV'
              AND VALIDFROM <= ?
              AND VALIDUNTIL >= ?
        """.format(t_302v=t_302v)
        cur = self._conn.cursor()
        cur.execute(sql, (self.client, company, lvdate, lvdate))
        row = cur.fetchone()
        if row is None:
            return False
        return _as_bool(row[0])

    def get_ihbday_brackets(self, company: str) -> List[IHBDayBracket]:
        """HCMSVRNREC.GETIHBDAY: IASHCM321 is goremezlik baz gun tablosu."""
        t_321 = self._table("IASHCM321")
        sql = """
            SELECT CODE, FIRSTMONTH, LASTMONTH, BASEDAY, UNIONDAY
            FROM {t_321}
            WHERE CLIENT = ?
              AND COMPANY = ?
            ORDER BY CODE
        """.format(t_321=t_321)
        cur = self._conn.cursor()
        try:
            cur.execute(sql, (self.client, company))
        except Exception:
            # UNIONDAY kolonu yoksa sendikasiz baz gun ile devam et
            cur.execute(
                f"SELECT CODE, FIRSTMONTH, LASTMONTH, BASEDAY, 0 FROM {t_321} "
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
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
        for fmt in ("%d.%m.%Y", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
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
