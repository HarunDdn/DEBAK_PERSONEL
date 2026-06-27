from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import get_connection
from app.models import ErrorResponse, LeaveBalanceResponse
from app.services.leave_balance import LeaveBalanceService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="CANIAS Personel İzin Bakiyesi API",
    description="IASHCMLVGRP tablosundan personel izin bakiyelerini (REM1-REM4) çeker.",
    version="1.0.0",
)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(
    "/api/leave-balance/{persid}",
    response_model=LeaveBalanceResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Personel izin bakiyesini getir",
    description=(
        "HCMT101D001.GETREMAININGDAYS ile aynı mantıkla REM1-REM4 alanlarını döner. "
        "REM1=Diğer Ücretsiz İzin, REM2=Yıllık İzin, REM3=Hastalık İzni, REM4=Ücretli Mazeret İzni"
    ),
)
async def get_leave_balance(persid: str) -> LeaveBalanceResponse:
    settings = get_settings()
    try:
        with get_connection() as connection:
            service = LeaveBalanceService(connection, settings)
            return service.get_leave_balance(persid.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Veritabanı hatası: {exc}",
        ) from exc


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/leave-balance", response_model=LeaveBalanceResponse)
async def get_leave_balance_query(
    persid: str = Query(..., description="Personel numarası (IASHCMLVGRP.PERSID)"),
) -> LeaveBalanceResponse:
    return await get_leave_balance(persid)
