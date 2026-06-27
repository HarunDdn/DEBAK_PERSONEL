#!/usr/bin/env python3
"""Veritabani baglantisi ve GR01 kidem dilimlerini dogrulama scripti.

Kullanim:
    python scripts/smoke_test.py
    python scripts/smoke_test.py 1028
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.constants import GR01_ANNUAL_LEAVE_BRACKETS
from app.db import get_connection
from app.providers import SqlLeaveDataProvider


def main() -> int:
    settings = get_settings()
    persid = sys.argv[1] if len(sys.argv) > 1 else "1028"

    print("=== Baglanti ===")
    print(f"  Server   : {settings.canias_db_server}")
    print(f"  Database : {settings.canias_db_name}")
    print(f"  User     : {settings.canias_db_user}")

    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            print("  Durum    : OK\n")
    except Exception as exc:
        print(f"  Durum    : HATA - {exc}\n")
        return 1

    print("=== GR01 (Yillik Izin) kidem dilimleri ===")
    with get_connection() as conn:
        provider = SqlLeaveDataProvider(
            conn, client=settings.canias_client, langu=settings.canias_langu
        )
        hcm213 = provider.get_hcm213(settings.canias_default_company, "GR01")
        if hcm213 is None:
            print("  GR01 bulunamadi!")
            return 1
        for b in hcm213.brackets:
            print(f"  {b.firstyear:>2}-{b.lastyear:<2} yil -> {b.lvdays} gun")
        for ref in GR01_ANNUAL_LEAVE_BRACKETS:
            match = next(
                (x for x in hcm213.brackets if x.firstyear == ref.firstyear), None
            )
            if match is None or match.lvdays != ref.lvdays:
                print(f"\n  UYARI: {ref.firstyear}. yil dilimi beklenen {ref.lvdays}, "
                      f"DB'de {match.lvdays if match else 'yok'}")
            else:
                print(f"  [OK] {ref.firstyear}-{ref.lastyear} -> {ref.lvdays}")

    print(f"\n=== PERSID {persid} izin gruplari ===")
    from app.canias_leave import LeaveCalculator

    with get_connection() as conn:
        provider = SqlLeaveDataProvider(
            conn, client=settings.canias_client, langu=settings.canias_langu
        )
        calc = LeaveCalculator(
            provider,
            default_company=settings.canias_default_company,
            default_plant=settings.canias_default_plant,
            sendika=settings.canias_sendika,
        )
        try:
            results = calc.get_remaining_days(persid)
        except Exception as exc:
            print(f"  HATA: {exc}")
            return 1
        for r in results:
            print(
                f"  REM{r.index}: {r.remaining_days:>6.1f} gun  "
                f"({r.name}, {r.leavegrp})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
