"""Common tool types shared across the state layer and tool surface."""

from __future__ import annotations

from typing import Any, Generic, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GroupLibrary(BaseModel):
    """A specific Zotero group library selected by id."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["group"] = "group"
    group_id: str


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# A library selector is either one of the bare keywords or a specific group.
LibrarySelector = Union[Literal["personal", "group", "all"], GroupLibrary]


class ItemRef(_StrictModel):
    """A reference to a Zotero library item.

    ``citekey`` is populated only when Better BibTeX can resolve it; it is never
    invented.
    """

    zotero_key: str
    library: LibrarySelector = "personal"
    citekey: Optional[str] = None


class PassageRef(_StrictModel):
    """A located passage within an item's attachment, with the verbatim quote."""

    item: ItemRef
    attachment_key: Optional[str] = None
    page: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: str


class Provenance(_StrictModel):
    """Provenance stamped on every tool result."""

    tool: str
    tool_version: str
    ran_at: str
    config_hash: str
    sources: list[dict[str, str]] = Field(default_factory=list)


class ToolError(_StrictModel):
    code: str
    message: str
    remediation: Optional[str] = None


T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Discriminated tool result. ``ok`` selects ``data`` vs ``error``."""

    model_config = ConfigDict(extra="forbid")
    ok: bool
    data: Optional[T] = None
    error: Optional[ToolError] = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Optional[Provenance] = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "ToolResult[T]":
        if self.ok and self.error is not None:
            raise ValueError("ok result must not carry an error")
        if not self.ok and self.error is None:
            raise ValueError("failed result must carry an error")
        return self

    @classmethod
    def success(cls, data: Any, *, provenance: Provenance | None = None,
                warnings: list[str] | None = None) -> "ToolResult[Any]":
        return cls(ok=True, data=data, provenance=provenance, warnings=warnings or [])

    @classmethod
    def failure(cls, code: str, message: str,
                remediation: str | None = None) -> "ToolResult[Any]":
        return cls(ok=False, error=ToolError(code=code, message=message,
                                             remediation=remediation))
