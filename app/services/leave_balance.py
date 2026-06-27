"""Personel izin bakiyesi servisi (main dal API uyumlulugu).

Trace tabanli LeaveCalculator uzerine ince bir katman; HTML arayuzunun
bekledigi LeaveBalanceResponse formatini uretir.
"""
from __future__ import annotations

from datetime import date

from app.canias_leave import LeaveCalculator, PersonnelNotFound
from app.config import Settings
from app.providers import SqlLeaveDataProvider
from app.schemas import LeaveBalanceItem, LeaveBalanceResponse


class LeaveBalanceService:
    """CANIAS HCMT101D001.GETREMAININGDAYS mantigini sunar."""

    def __init__(self, connection, settings: Settings, as_of: date | None = None):
        self.connection = connection
        self.settings = settings
        self.query_date = as_of or date.today()
        self.provider = SqlLeaveDataProvider(
            connection,
            client=settings.canias_client,
            langu=settings.canias_langu,
        )
        self.calculator = LeaveCalculator(
            self.provider,
            default_company=settings.canias_default_company,
            default_plant=settings.canias_default_plant,
            sendika=settings.canias_sendika,
            as_of=self.query_date,
        )

    def get_leave_balance(self, persid: str) -> LeaveBalanceResponse:
        persid = persid.strip()
        master = self.provider.get_personnel_master(persid)
        if master is None:
            raise ValueError(f"Personel bulunamadi: {persid}")

        try:
            results = self.calculator.get_remaining_days(persid)
        except PersonnelNotFound as exc:
            raise ValueError(str(exc)) from exc

        if not results:
            raise ValueError(f"Personel icin izin grubu kaydi bulunamadi: {persid}")

        balances = [
            LeaveBalanceItem(
                rem_field=f"REM{r.index}",
                leave_code=r.leavecode,
                leave_name=r.name,
                leave_group=r.leavegrp,
                remaining_days=r.remaining_days,
                total_earned=r.earned_days,
                used_days=r.carried_used,
                leave_days=r.used_in_period,
                seniority_years=r.seniority_years,
            )
            for r in results
        ]

        return LeaveBalanceResponse(
            persid=persid,
            display_name=master.display or None,
            company=master.company,
            plant=master.plant,
            query_date=self.query_date,
            balances=balances,
        )
