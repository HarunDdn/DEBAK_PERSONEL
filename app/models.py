from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LeaveBalanceItem(BaseModel):
    rem_field: str = Field(description="REM1, REM2, REM3 veya REM4")
    leave_code: str
    leave_name: str
    leave_group: str
    remaining_days: float
    total_earned: float
    used_days: float
    leave_days: float
    seniority_date: date | None = None


class LeaveBalanceResponse(BaseModel):
    persid: str
    display_name: str | None = None
    company: str | None = None
    plant: str | None = None
    query_date: date
    balances: list[LeaveBalanceItem]


class ErrorResponse(BaseModel):
    detail: str


def to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)
