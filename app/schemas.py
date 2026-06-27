"""API istek/yanit semalari (Pydantic)."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class RemainingLeaveItem(BaseModel):
    """Tek bir izin turu icin kalan gun bilgisi."""

    index: int = Field(..., description="REM1, REM2, ... sirasi")
    field: str = Field(..., description="CANIAS alan adi: REM1/REM2/...")
    leavecode: str = Field(..., description="IASHCMLVGRP.LEAVECODE")
    leavegrp: str = Field(..., description="IASHCMLVGRP.LEAVEGRP")
    name: str = Field(..., description="Izin adi (IASHCM306X.STEXT)")
    remaining_days: float = Field(..., description="HCMLVGRP_REMLVDAYS (kalan gun)")
    earned_days: float = Field(..., description="HCMLVGRP_TOTEARNED (kazanilan)")
    used_in_period: float = Field(..., description="HCMLVGRP_LVDAYS (donemde kullanilan)")
    carried_used: float = Field(..., description="HCMLVGRP_USEDDAY (devreden kullanim)")
    seniority_years: int = Field(..., description="HCMLVGRP_SENYEAR (kidem yili)")


class RemainingLeaveResponse(BaseModel):
    """`/personnel/{persid}/remaining-leaves` yaniti."""

    persid: str
    company: Optional[str] = None
    as_of: str = Field(..., description="Hesaplama tarihi (PLVDATE)")
    items: List[RemainingLeaveItem]


class LeaveBalanceItem(BaseModel):
    """`/api/leave-balance/{persid}` yanit satiri (main dal uyumlulugu)."""

    rem_field: str = Field(description="REM1, REM2, REM3 veya REM4")
    leave_code: str
    leave_name: str
    leave_group: str
    remaining_days: float
    total_earned: float
    used_days: float
    leave_days: float
    seniority_date: date | None = None
    seniority_years: int = 0


class LeaveBalanceResponse(BaseModel):
    """Web arayuzu ve `/api/leave-balance` yaniti."""

    persid: str
    display_name: str | None = None
    company: str | None = None
    plant: str | None = None
    query_date: date
    balances: list[LeaveBalanceItem]


class ErrorResponse(BaseModel):
    detail: str
