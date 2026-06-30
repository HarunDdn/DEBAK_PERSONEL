"""HCMT34 personel izin listesi servisi."""
from __future__ import annotations

from datetime import date

from app.canias_leave_days import LeaveDayCalculator, current_month_period
from app.config import Settings
from app.constants import CONFIRMSTAT_LABELS, LVSTAT_LABELS
from app.providers import SqlLeaveDataProvider, _format_date_x, _format_time_value
from app.schemas import PersonnelLeaveItem, PersonnelLeaveResponse


class PersonnelLeaveService:
    """CANIAS HCMT34D502 / HCMLEAVEREC.GETPERSLEAVES mantigini sunar."""

    def __init__(self, connection, settings: Settings, as_of: date | None = None):
        self.settings = settings
        self.as_of = as_of or date.today()
        self.provider = SqlLeaveDataProvider(
            connection,
            client=settings.canias_client,
            langu=settings.canias_langu,
            db_schema=settings.canias_db_schema,
        )
        self.calculator = LeaveDayCalculator(self.provider)

    def get_personnel_leaves(
        self,
        persid: str,
        *,
        leavecode: str | None = None,
    ) -> PersonnelLeaveResponse:
        persid = persid.strip()
        master = self.provider.get_personnel_master(persid)
        if master is None:
            raise ValueError(f"Personel bulunamadi: {persid}")

        company = master.company or self.settings.canias_default_company
        plant = master.plant or self.settings.canias_default_plant
        period_start, period_end = current_month_period(self.as_of)

        raw_rows = self.provider.get_raw_personnel_leaves(
            persid,
            company,
            plant,
            period_start,
            period_end,
            leavecode=leavecode.strip() if leavecode else None,
        )

        items: list[PersonnelLeaveItem] = []
        for raw in raw_rows:
            totleaveday = self.calculator.calc_totleaveday(
                raw,
                persid=persid,
                period_start=period_start,
                period_end=period_end,
                calendar=master.calendar,
            )
            clipped_first = max(raw.firstdate, period_start)
            clipped_last = min(raw.lastdate, period_end)
            items.append(
                PersonnelLeaveItem(
                    leavenum=raw.leavenum,
                    LEAVECODE=raw.leavecode_text,
                    leavecode=raw.leavecode,
                    CONFIRMSTAT=CONFIRMSTAT_LABELS.get(
                        raw.confirmstat, str(raw.confirmstat)
                    ),
                    confirmstat=raw.confirmstat,
                    LVSTAT=LVSTAT_LABELS.get(raw.lvstat, str(raw.lvstat)),
                    lvstat=raw.lvstat,
                    FIRSTDATEX=_format_date_x(clipped_first),
                    FIRSTTIME=_format_time_value(raw.firsttime),
                    LASTDATEX=_format_date_x(clipped_last),
                    LASTTIME=_format_time_value(raw.lasttime),
                    TOTLEAVEDAY=totleaveday,
                )
            )

        return PersonnelLeaveResponse(
            persid=persid,
            display_name=master.display or None,
            company=company,
            plant=plant,
            period_start=period_start,
            period_end=period_end,
            items=items,
            total_leave_days=round(sum(i.TOTLEAVEDAY for i in items), 2),
        )
