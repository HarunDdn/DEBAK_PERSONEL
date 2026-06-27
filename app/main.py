"""FastAPI web servisi: personel numarasina gore kalan izin gunleri."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.canias_leave import PersonnelNotFound
from app.config import get_settings
from app.db import get_connection
from app.providers import SqlLeaveDataProvider
from app.schemas import (
    ErrorResponse,
    LeaveBalanceResponse,
    RemainingLeaveItem,
    RemainingLeaveResponse,
)
from app.services.leave_balance import LeaveBalanceService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="CANIAS HCM - Kalan Izin Servisi",
    description=(
        "IASHCMLVGRP.PERSID'ye gore personelin kalan izin gunlerini "
        "(REM1, REM2, ...) CANIAS HCMT101 SETREMLVDAYS mantigiyla hesaplar."
    ),
    version="1.0.0",
)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/api/leave-balance/{persid}",
    response_model=LeaveBalanceResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["leaves"],
)
async def get_leave_balance(
    persid: str,
    as_of: Optional[date] = Query(None, description="Hesaplama tarihi (PLVDATE)"),
) -> LeaveBalanceResponse:
    settings = get_settings()
    try:
        with get_connection() as connection:
            service = LeaveBalanceService(connection, settings, as_of=as_of)
            return service.get_leave_balance(persid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Hesaplama hatasi: {exc}") from exc


@app.get("/api/leave-balance", response_model=LeaveBalanceResponse, tags=["leaves"])
async def get_leave_balance_query(
    persid: str = Query(..., description="Personel numarasi (IASHCMLVGRP.PERSID)"),
    as_of: Optional[date] = Query(None, description="Hesaplama tarihi (PLVDATE)"),
) -> LeaveBalanceResponse:
    return await get_leave_balance(persid, as_of=as_of)


@app.get(
    "/personnel/{persid}/remaining-leaves",
    response_model=RemainingLeaveResponse,
    tags=["leaves"],
)
def remaining_leaves(
    persid: str,
    as_of: Optional[date] = Query(None, description="Hesaplama tarihi (PLVDATE)"),
) -> RemainingLeaveResponse:
    """Detayli kalan izin yaniti (trace alan adlariyla)."""
    settings = get_settings()
    try:
        with get_connection() as conn:
            service = LeaveBalanceService(conn, settings, as_of=as_of)
            balance = service.get_leave_balance(persid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PersonnelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Hesaplama hatasi: {exc}") from exc

    items = [
        RemainingLeaveItem(
            index=i + 1,
            field=b.rem_field,
            leavecode=b.leave_code,
            leavegrp=b.leave_group,
            name=b.leave_name,
            remaining_days=b.remaining_days,
            earned_days=b.total_earned,
            used_in_period=b.leave_days,
            carried_used=b.used_days,
            seniority_years=b.seniority_years,
        )
        for i, b in enumerate(balance.balances)
    ]
    return RemainingLeaveResponse(
        persid=persid,
        company=balance.company,
        as_of=balance.query_date.isoformat(),
        items=items,
    )
