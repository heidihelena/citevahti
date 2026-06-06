"""PRISMA validators: human-only decisions, allowed stages/decisions, reasons."""

from __future__ import annotations

from ..schemas.prisma import (
    PRISMA_DECIDERS,
    PRISMA_DECISIONS,
    PRISMA_STAGES,
    PrismaDecision,
    PrismaLedgerRecord,
)
from .errors import ValidationError


class PrismaError(ValidationError):
    code = "prisma_invalid"


def validate_decision(d: PrismaDecision) -> None:
    if d.decider not in PRISMA_DECIDERS:
        raise PrismaError(f"decider must be one of {PRISMA_DECIDERS}; AI votes are not decisions")
    if d.stage not in PRISMA_STAGES:
        raise PrismaError(f"unsupported stage {d.stage!r}")
    if d.decision not in PRISMA_DECISIONS:
        raise PrismaError(f"unsupported decision {d.decision!r}")
    if d.decision == "exclude" and not d.reason:
        raise PrismaError("an 'exclude' decision requires a reason")


def validate_ledger(rec: PrismaLedgerRecord) -> None:
    for d in rec.decisions:
        validate_decision(d)
