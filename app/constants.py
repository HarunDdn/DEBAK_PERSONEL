"""CANIAS izin grubu sabitleri (kurum onayli).

GR01 (Yillik Izin) kidem dilimleri IASHCM213D tablosundan da okunur;
asagidaki degerler kurum tarafindan dogrulanmistir ve testlerde referans alinir.
"""
from __future__ import annotations

from app.models import HCM213Bracket

# GR01 - Yillik Izin (LVGRPTYPE=1, DAYTRANSFER=1)
GR01_ANNUAL_LEAVE_BRACKETS: tuple[HCM213Bracket, ...] = (
    HCM213Bracket(ordnum=1, firstyear=1, lastyear=5, lvdays=14.0),
    HCM213Bracket(ordnum=2, firstyear=6, lastyear=14, lvdays=20.0),
    HCM213Bracket(ordnum=3, firstyear=15, lastyear=99, lvdays=26.0),
)
