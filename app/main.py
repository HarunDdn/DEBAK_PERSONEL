"""FastAPI web servisi: personel numarasina gore kalan izin gunleri.

Calistirma:
    uvicorn app.main:app --reload

Ornek:
    GET /personnel/1028/remaining-leaves
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .canias_leave import LeaveCalculator, PersonnelNotFound
from .config import get_settings
from .db import get_connection
from .providers import SqlLeaveDataProvider
from .schemas import RemainingLeaveItem, RemainingLeaveResponse

app = FastAPI(
    title="CANIAS HCM - Kalan Izin Servisi",
    description=(
        "IASHCMLVGRP.PERSID'ye gore personelin kalan izin gunlerini "
        "(REM1, REM2, ...) CANIAS HCMT101 mantigiyla hesaplar."
    ),
    version="1.0.0",
)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/personnel/{persid}/remaining-leaves",
    response_model=RemainingLeaveResponse,
    tags=["leaves"],
)
def remaining_leaves(
    persid: str,
    as_of: Optional[date] = Query(
        None, description="Hesaplama tarihi (varsayilan: bugun). PLVDATE."
    ),
) -> RemainingLeaveResponse:
    """Verilen personel numarasi icin kalan izin gunlerini dondurur."""
    settings = get_settings()
    try:
        with get_connection() as conn:
            provider = SqlLeaveDataProvider(
                conn, client=settings.canias_client, langu=settings.canias_langu
            )
            calculator = LeaveCalculator(
                provider,
                default_company=settings.canias_default_company,
                default_plant=settings.canias_default_plant,
                sendika=settings.canias_sendika,
                as_of=as_of,
            )
            results = calculator.get_remaining_days(persid)
            company = provider.get_personnel_master(persid)
    except PersonnelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - calisma zamani hatalari
        raise HTTPException(status_code=500, detail=f"Hesaplama hatasi: {exc}") from exc

    items = [
        RemainingLeaveItem(
            index=r.index,
            field=f"REM{r.index}",
            leavecode=r.leavecode,
            leavegrp=r.leavegrp,
            name=r.name,
            remaining_days=r.remaining_days,
            earned_days=r.earned_days,
            used_in_period=r.used_in_period,
            carried_used=r.carried_used,
            seniority_years=r.seniority_years,
        )
        for r in results
    ]
    return RemainingLeaveResponse(
        persid=persid,
        company=company.company if company else None,
        as_of=(as_of or date.today()).isoformat(),
        items=items,
    )
