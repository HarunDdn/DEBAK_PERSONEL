"""Testler icin in-memory sahte veri saglayici.

CANIAS trace dosyasindaki (PERSID 1028) senaryoyu temsil eder.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.models import (
    HCM213Bracket,
    HCM213Settings,
    IHBDayBracket,
    LeaveGroupRow,
    LeaveRecord,
    PersonnelMaster,
)


class FakeProvider:
    """Bellek ici test saglayicisi (LeaveDataProvider protokolu)."""

    def __init__(
        self,
        master: Optional[PersonnelMaster],
        leave_groups: List[LeaveGroupRow],
        hcm213: dict[str, HCM213Settings],
        leaves: dict[str, List[LeaveRecord]] | None = None,
        excluded: dict[int, List[LeaveRecord]] | None = None,
        excsenlv: bool = False,
        ihb: List[IHBDayBracket] | None = None,
    ):
        self._master = master
        self._leave_groups = leave_groups
        self._hcm213 = hcm213
        self._leaves = leaves or {}
        self._excluded = excluded or {}
        self._excsenlv = excsenlv
        self._ihb = ihb or []

    def get_personnel_master(self, persid: str) -> Optional[PersonnelMaster]:
        return self._master

    def get_leave_groups(self, persid: str, company: str) -> List[LeaveGroupRow]:
        return self._leave_groups

    def get_hcm213(self, company: str, lvgroupid: str) -> Optional[HCM213Settings]:
        return self._hcm213.get(lvgroupid)

    def get_leaves_for_lvcode(
        self, persid: str, lvcode: str, maxdate: date, psendate: date
    ) -> List[LeaveRecord]:
        out = []
        for rec in self._leaves.get(lvcode, []):
            if rec.firstdate <= maxdate and (
                rec.lastdate > psendate
                or (rec.firstdate == psendate and rec.lastdate == psendate)
            ):
                out.append(rec)
        return out

    def get_excluded_leaves(
        self, persid: str, lvdate: date, lvsendt: date, excludedsen: int
    ) -> List[LeaveRecord]:
        out = []
        for rec in self._excluded.get(excludedsen, []):
            if rec.firstdate <= lvdate and rec.lastdate >= lvsendt:
                out.append(rec)
        return out

    def has_excsenlv_param(self, company: str, lvdate: date) -> bool:
        return self._excsenlv

    def get_ihbday_brackets(self, company: str) -> List[IHBDayBracket]:
        return self._ihb
