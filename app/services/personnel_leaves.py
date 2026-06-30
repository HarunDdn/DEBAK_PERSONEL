"""HCMT34 personel izin listesi servisi."""
from __future__ import annotations

from datetime import date, timedelta

from app.config import Settings
from app.constants import CONFIRMSTAT_LABELS, LVSTAT_LABELS
from app.providers import SqlLeaveDataProvider
from app.schemas import PersonnelLeaveItem, PersonnelLeaveResponse


class PersonnelLeaveService:
    """CANIAS HCMT34D502 / HCMLEAVEREC.GETPERSLEAVES mantigini sunar."""

    def __init__(self, connection, settings: Settings):
        self.settings = settings
        self.provider = SqlLeaveDataProvider(
            connection,
            client=settings.canias_client,
            langu=settings.canias_langu,
            db_schema=settings.canias_db_schema,
        )

    def get_personnel_leaves(
        self,
        persid: str,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
        leavecode: str | None = None,
    ) -> PersonnelLeaveResponse:
        persid = persid.strip()
        master = self.provider.get_personnel_master(persid)
        if master is None:
            raise ValueError(f"Personel bulunamadi: {persid}")

        company = master.company or self.settings.canias_default_company
        plant = master.plant or self.settings.canias_default_plant

        start = period_start or date(date.today().year, date.today().month, 1)
        end = period_end or _last_day_of_month(start)

        rows = self.provider.get_personnel_leaves(
            persid,
            company,
            plant,
            start,
            end,
            leavecode=leavecode.strip() if leavecode else None,
        )

        items = [
            PersonnelLeaveItem(
                leavenum=r.leavenum,
                LEAVECODE=r.leavecode_text,
                leavecode=r.leavecode,
                CONFIRMSTAT=CONFIRMSTAT_LABELS.get(r.confirmstat, str(r.confirmstat)),
                confirmstat=r.confirmstat,
                LVSTAT=LVSTAT_LABELS.get(r.lvstat, str(r.lvstat)),
                lvstat=r.lvstat,
                FIRSTDATEX=r.firstdatex,
                FIRSTTIME=r.firsttime,
                LASTDATEX=r.lastdatex,
                LASTTIME=r.lasttime,
                TOTLEAVEDAY=r.totleaveday,
            )
            for r in rows
        ]

        return PersonnelLeaveResponse(
            persid=persid,
            display_name=master.display or None,
            company=company,
            plant=plant,
            period_start=start,
            period_end=end,
            items=items,
            total_leave_days=round(sum(i.TOTLEAVEDAY for i in items), 2),
        )


def _last_day_of_month(value: date) -> date:
    if value.month == 12:
        return date(value.year, 12, 31)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)
