from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.engine import Connection

from app.config import Settings
from app.models import LeaveBalanceItem, LeaveBalanceResponse, to_float
from app.queries import (
    CONSTANT_LEAVE_DAYS_QUERY,
    EXCLUDED_SENIORITY_DAYS_QUERY,
    LEAVE_GROUPS_QUERY,
    LEAVE_GROUP_DEFINITION_QUERY,
    PERSONNEL_CONTEXT_QUERY,
    SENIORITY_LEAVE_DAYS_QUERY,
    USED_LEAVE_DAYS_QUERY,
)


# Log dosyasındaki izin kodu → REM alanı eşlemesi (LEAVECODE sırasına göre)
KNOWN_LEAVE_CODES = {
    "0003": "REM1",  # Diğer Ücretsiz İzin
    "0005": "REM2",  # Yıllık İzin
    "0008": "REM3",  # Hastalık İzni (Ödemesiz)
    "0014": "REM4",  # Ücretli Mazeret İzni
}

REM_FIELDS = ["REM1", "REM2", "REM3", "REM4"]


class LeaveBalanceService:
    """
    CANIAS HCMT101D001.GETREMAININGDAYS + HCMLEAVEREC.SETREMLVDAYS mantığını uygular.

    Formül (log satır 58):
        HCMLVGRP_REMLVDAYS = TOTEARNED - LVDAYS - USEDDAY
    """

    def __init__(self, connection: Connection, settings: Settings):
        self.connection = connection
        self.settings = settings
        self.query_date = date.today()

    def get_leave_balance(self, persid: str) -> LeaveBalanceResponse:
        personnel = self._fetch_personnel(persid)
        if not personnel:
            raise ValueError(f"Personel bulunamadı: {persid}")

        leave_groups = self._fetch_leave_groups(persid, personnel["COMPANY"])
        if not leave_groups:
            raise ValueError(f"Personel için izin grubu kaydı bulunamadı: {persid}")

        balances: list[LeaveBalanceItem] = []
        for index, row in enumerate(leave_groups[:4]):
            rem_field = REM_FIELDS[index]
            balance = self._calculate_row_balance(row, personnel, rem_field)
            balances.append(balance)

        return LeaveBalanceResponse(
            persid=persid,
            display_name=personnel.get("DISPLAY"),
            company=personnel.get("COMPANY"),
            plant=personnel.get("PLANT"),
            query_date=self.query_date,
            balances=balances,
        )

    def _fetch_personnel(self, persid: str) -> dict[str, Any] | None:
        from app.database import fetch_one

        return fetch_one(
            self.connection,
            PERSONNEL_CONTEXT_QUERY,
            {
                "client": self.settings.canias_client,
                "persid": persid,
            },
        )

    def _fetch_leave_groups(self, persid: str, company: str) -> list[dict[str, Any]]:
        from app.database import fetch_all

        return fetch_all(
            self.connection,
            LEAVE_GROUPS_QUERY,
            {
                "client": self.settings.canias_client,
                "persid": persid,
                "company": company,
                "language": self.settings.canias_language,
            },
        )

    def _calculate_row_balance(
        self,
        row: dict[str, Any],
        personnel: dict[str, Any],
        rem_field: str,
    ) -> LeaveBalanceItem:
        leave_code = str(row["LEAVECODE"]).strip()
        leave_group = str(row["LEAVEGRP"]).strip()
        seniority_date = self._as_date(row.get("LEAVESENDATE"))
        used_day = to_float(row.get("USEDDAY"))
        extra_year = int(to_float(row.get("EXTRAYEAR")))

        lv_days = self._get_leave_days(
            persid=str(personnel["PERSID"]),
            leave_code=leave_code,
            seniority_date=seniority_date,
            extra_year=extra_year,
        )

        total_earned = self._get_earned_leave_days(
            company=str(personnel["COMPANY"]),
            leave_group=leave_group,
            seniority_date=seniority_date,
            birth_date=self._as_date(personnel.get("BIRTHDAY")),
            persid=str(personnel["PERSID"]),
            extra_year=extra_year,
        )

        remaining = round(total_earned - lv_days - used_day, 2)

        return LeaveBalanceItem(
            rem_field=rem_field,
            leave_code=leave_code,
            leave_name=str(row.get("STEXT") or "").strip(),
            leave_group=leave_group,
            remaining_days=remaining,
            total_earned=total_earned,
            used_days=used_day,
            leave_days=lv_days,
            seniority_date=seniority_date,
        )

    def _get_leave_days(
        self,
        persid: str,
        leave_code: str,
        seniority_date: date | None,
        extra_year: int,
    ) -> float:
        from app.database import fetch_one

        if not seniority_date:
            return 0.0

        adjusted_seniority = self._subtract_years(seniority_date, extra_year)

        result = fetch_one(
            self.connection,
            USED_LEAVE_DAYS_QUERY,
            {
                "client": self.settings.canias_client,
                "persid": persid,
                "leavecode": leave_code,
                "control_date": self._max_control_date(),
                "seniority_date": adjusted_seniority,
            },
        )
        return to_float(result["LVDAYS"]) if result else 0.0

    def _get_earned_leave_days(
        self,
        company: str,
        leave_group: str,
        seniority_date: date | None,
        birth_date: date | None,
        persid: str,
        extra_year: int,
    ) -> float:
        from app.database import fetch_all, fetch_one

        group_def = fetch_one(
            self.connection,
            LEAVE_GROUP_DEFINITION_QUERY,
            {
                "client": self.settings.canias_client,
                "company": company,
                "leave_group": leave_group,
                "language": self.settings.canias_language,
            },
        )

        if not group_def or not seniority_date:
            return 0.0

        adjusted_seniority = self._subtract_years(seniority_date, extra_year)
        sen_year = self._year_diff(adjusted_seniority, self.query_date) + extra_year

        lv_type = str(group_def.get("LVTYPE") or "").strip()
        lv_calc_type = str(group_def.get("LVCALCTYPE") or "").strip()

        # Yıllık izin (GR01) — kıdeme göre hesap
        if lv_type in {"1", "Y"} or leave_group == "GR01":
            seniority_rows = fetch_all(
                self.connection,
                SENIORITY_LEAVE_DAYS_QUERY,
                {
                    "client": self.settings.canias_client,
                    "company": company,
                    "leave_group": leave_group,
                },
            )
            if seniority_rows:
                return self._calc_seniority_earned_days(seniority_rows, sen_year)

        # Sabit izin türleri (GR08 vb.) — IASHCM213D tablosundan
        constant_rows = fetch_all(
            self.connection,
            CONSTANT_LEAVE_DAYS_QUERY,
            {
                "client": self.settings.canias_client,
                "company": company,
                "leave_group": leave_group,
            },
        )

        if constant_rows:
            # GETCONSTYEARLV: kıdem yılına göre sabit gün
            ord_index = min(max(sen_year, 1), len(constant_rows)) - 1
            return to_float(constant_rows[ord_index].get("LVDAYS"))

        # Tanımsız grup — kıdem dışı günleri düşerek temel hesap
        if lv_calc_type:
            excluded = fetch_one(
                self.connection,
                EXCLUDED_SENIORITY_DAYS_QUERY,
                {
                    "client": self.settings.canias_client,
                    "persid": persid,
                    "control_date": self.query_date,
                    "seniority_date": adjusted_seniority,
                },
            )
            if excluded:
                return max(0.0, sen_year * 14 - to_float(excluded.get("EXCLUDED_DAYS")))

        return 0.0

    @staticmethod
    def _calc_seniority_earned_days(rows: list[dict[str, Any]], sen_year: int) -> float:
        """
        Yıllık izin kazanımı: her kıdem yılı için IASHCM213V satırındaki LVDAYS toplanır.
        Log örneği: 11 yıl kıdem → TOTEARNED = 190.0
        """
        if sen_year <= 0:
            return to_float(rows[0].get("LVDAYS"))

        total = 0.0
        for year_index in range(1, sen_year + 1):
            row_index = min(year_index, len(rows)) - 1
            total += to_float(rows[row_index].get("LVDAYS"))
        return total

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        return None

    @staticmethod
    def _subtract_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(year=value.year - years, day=28)

    @staticmethod
    def _year_diff(start: date, end: date) -> int:
        years = end.year - start.year
        if (end.month, end.day) < (start.month, start.day):
            years -= 1
        return max(years, 0)

    @staticmethod
    def _max_control_date() -> date:
        return date(2100, 1, 1)
