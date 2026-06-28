"""The shared rating frame: a version-stamped set of subjects + schemes + vocab.

A frame carries multiple co-existing schemes (Patch 3): GRADE certainty as the
primary outcome-level scheme, with RoB 2 / ROBINS-I as secondary study-level (or
study x outcome) risk-of-bias schemes. ``frame_id`` + ``frame_version`` are
recorded on every rating; aggregation refuses to mix frame versions or schemes.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ItemRef

SchemeKind = Literal["GRADE", "RoB2", "ROBINS-I", "Generic"]
SchemeUnit = Literal["outcome", "study", "study_x_outcome"]


class Level(BaseModel):
    """One controlled-vocabulary level.

    ``ordinal`` orders the level for ordinal-aware agreement statistics. A level
    may be non-ordinal (Patch 8): ROBINS-I "No information" is missing-like, not
    a point on the risk scale, so it carries ``ordinal=None`` and
    ``missing_like=True`` and is handled separately from ordered risk levels.
    """

    model_config = ConfigDict(extra="forbid")
    value: str
    ordinal: Optional[int] = None
    missing_like: bool = False

    @model_validator(mode="after")
    def _check(self) -> "Level":
        if not self.missing_like and self.ordinal is None:
            raise ValueError(
                f"level {self.value!r} must have an ordinal unless missing_like"
            )
        if self.missing_like and self.ordinal is not None:
            raise ValueError(
                f"missing_like level {self.value!r} must not have an ordinal"
            )
        return self


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain_id: str
    label: str


class Scheme(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheme_id: str
    kind: SchemeKind
    unit: SchemeUnit
    domains: Optional[list[Domain]] = None
    levels: list[Level]

    def level_values(self) -> set[str]:
        return {lvl.value for lvl in self.levels}

    def ordinal_levels(self) -> list[Level]:
        """Ordered, non-missing levels for ordinal-aware statistics."""
        ordered = [lvl for lvl in self.levels if not lvl.missing_like]

        # Non-missing_like levels always carry an ordinal — Level._check enforces it at
        # construction — so the `else` is unreachable; it only proves int-ness to mypy.
        return sorted(ordered, key=lambda lvl: lvl.ordinal if lvl.ordinal is not None else 0)


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_id: str
    label: str
    direction: Optional[str] = None


class Study(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_id: str
    item: ItemRef


class Pico(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p: Optional[str] = None
    i: Optional[str] = None
    c: Optional[str] = None
    o: list[str] = Field(default_factory=list)


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: str
    frame_version: str
    created_at: str
    pico: Optional[Pico] = None
    outcomes: list[Outcome] = Field(default_factory=list)
    studies: list[Study] = Field(default_factory=list)
    schemes: list[Scheme] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> "Frame":
        for label, ids in (
            ("scheme_id", [s.scheme_id for s in self.schemes]),
            ("outcome_id", [o.outcome_id for o in self.outcomes]),
            ("study_id", [s.study_id for s in self.studies]),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} in frame {self.frame_id}")
        return self

    def get_scheme(self, scheme_id: str) -> Optional[Scheme]:
        return next((s for s in self.schemes if s.scheme_id == scheme_id), None)

    def has_outcome(self, outcome_id: str) -> bool:
        return any(o.outcome_id == outcome_id for o in self.outcomes)

    def has_study(self, study_id: str) -> bool:
        return any(s.study_id == study_id for s in self.studies)
