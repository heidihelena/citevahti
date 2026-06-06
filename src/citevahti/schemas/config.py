"""``.citevahti/config.json`` schema and default factory.

Folds in the sign-off patches:
- Patch 1: AI model pin defaults to PENDING sentinels; must be explicitly set.
- Patch 2: AI rating tasks are split from assist tasks; ``screen_vote`` is
  optional and disabled by default.
- Patch 3/10: GRADE certainty (``High|Moderate|Low|Very Low``, stored exactly)
  is the primary outcome-level scheme; RoB2/ROBINS-I are secondary.
- Patch 8: ROBINS-I "No information" is missing-like, not ordinal.
"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import (
    PENDING_MODEL_ID,
    PENDING_MODEL_SNAPSHOT,
    SCHEMA_VERSION,
)
from .common import LibrarySelector
from .frame import Level, SchemeKind, SchemeUnit


class Endpoints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zotero_api: str = "http://localhost:23119/api/"
    bbt_jsonrpc: str = "http://localhost:23119/better-bibtex/json-rpc"
    bbt_cayw: str = "http://localhost:23119/better-bibtex/cayw"


class ZoteroConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: str = "~/Zotero"
    probed_version: Optional[str] = None
    version_status: Optional[Literal["parsed", "unknown"]] = None
    api_mode: Literal["read_only"] = "read_only"
    # non-secret identifiers captured at onboarding (secrets live in the keyring)
    user_id: Optional[str] = None
    library_type: Literal["user", "group"] = "user"
    library_id: Optional[str] = None
    default_collection_key: Optional[str] = None


class RateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    with_key_rps: int = 10
    without_key_rps: int = 3


class PubMedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["ncbi_eutils"] = "ncbi_eutils"
    email_env: str = "NCBI_EMAIL"
    api_key_env: str = "NCBI_API_KEY"
    contact_email: Optional[str] = None     # non-secret; captured at onboarding
    rate_limit: RateLimit = Field(default_factory=RateLimit)


class SchemeSpec(BaseModel):
    """A scheme template recorded in config; frames instantiate from these."""

    model_config = ConfigDict(extra="forbid")
    scheme_id: str
    kind: SchemeKind
    unit: SchemeUnit
    levels: list[Level]
    reasons_optional: bool = True

    @field_validator("levels", mode="before")
    @classmethod
    def _coerce_string_levels(cls, v):
        """Accept ``["High", "Moderate", ...]`` and assign descending ordinals.

        First entry is treated as the highest certainty/least risk. Explicit
        ``Level`` dicts are passed through unchanged (needed for missing_like).
        """
        if not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v):
            return v
        n = len(v)
        return [{"value": val, "ordinal": n - i} for i, val in enumerate(v)]


class AIProvenanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    provider: str = "anthropic"
    # Patch 1: never pin a model implicitly.
    model_id: str = PENDING_MODEL_ID
    model_snapshot: str = PENDING_MODEL_SNAPSHOT
    prompt_template_version: str = "unset"
    config_hash_method: Literal["sha256_canonical_json"] = "sha256_canonical_json"
    # Patch 2: rating tasks vs assist tasks are distinct sets.
    allowed_rating_tasks: list[str] = Field(default_factory=lambda: ["extract", "assess"])
    optional_rating_tasks: list[str] = Field(default_factory=lambda: ["screen_vote"])
    allowed_assist_tasks: list[str] = Field(default_factory=lambda: ["claim_check"])
    # ``screen_vote`` is optional and OFF by default; metrics-only, never a decision.
    screen_vote_enabled: bool = False

    def is_model_pinned(self) -> bool:
        return (
            self.model_id != PENDING_MODEL_ID
            and self.model_snapshot != PENDING_MODEL_SNAPSHOT
            and bool(self.model_id)
            and bool(self.model_snapshot)
        )

    def effective_rating_tasks(self) -> set[str]:
        tasks = set(self.allowed_rating_tasks)
        if self.screen_vote_enabled:
            tasks |= set(self.optional_rating_tasks)
        return tasks


class RatingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: Literal["human_first_ai_blind", "ai_first_human_blind", "parallel_blind"] = (
        "human_first_ai_blind"
    )
    primary_scheme: SchemeSpec
    secondary_schemes: list[SchemeSpec] = Field(default_factory=list)


class WritebackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local_addon_preferred", "web_api", "disabled"] = "local_addon_preferred"
    web_api: Literal["opt_in", "off"] = "opt_in"
    silent_fallback: Literal[False] = False  # no silent local -> Web-API fallback, ever
    dry_run_default: bool = True
    # step 9: guarded write-back is opt-in and disabled by default
    enabled: bool = False
    kind: Literal["local_addon", "web_api", "unavailable"] = "unavailable"
    confirm_required: bool = True
    # web_api backend (Zotero Web API). The API key is read from env at runtime,
    # never stored in config; user/library id is needed to address the library.
    api_key_env: str = "ZOTERO_API_KEY"
    web_api_user_id: Optional[str] = None
    web_api_base: str = "https://api.zotero.org"
    default_collection_key: Optional[str] = None


class ValidationWarehouseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The de-identified validation warehouse (ADR-0001 D4). OFF by default —
    # nothing is collected without explicit consent.
    enabled: bool = False
    # Claim text is the top-sensitivity tier: stored only on a SECOND explicit
    # opt-in. With it off, the warehouse keeps only a one-way claim-text hash.
    include_claim_text: bool = False
    # auto-emit a record when a final decision is recorded (labels emerge from the
    # workflow); still gated by `enabled`.
    auto_emit: bool = False
    domain: Optional[str] = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    endpoints: Endpoints = Field(default_factory=Endpoints)
    zotero: ZoteroConfig = Field(default_factory=ZoteroConfig)
    default_library: LibrarySelector = "personal"
    pubmed: PubMedConfig = Field(default_factory=PubMedConfig)
    rating: RatingConfig
    ai_provenance: AIProvenanceConfig = Field(default_factory=AIProvenanceConfig)
    writeback: WritebackConfig = Field(default_factory=WritebackConfig)
    validation_warehouse: ValidationWarehouseConfig = Field(
        default_factory=ValidationWarehouseConfig)
    # where secrets live; config NEVER stores the secret values themselves
    secrets_backend: Literal["system_keyring", "env"] = "system_keyring"

    @staticmethod
    def default() -> "Config":
        """Build the default config with GRADE primary + RoB2/ROBINS-I secondary."""
        grade = SchemeSpec(
            scheme_id="grade_certainty",
            kind="GRADE",
            unit="outcome",
            levels=[
                Level(value="High", ordinal=4),
                Level(value="Moderate", ordinal=3),
                Level(value="Low", ordinal=2),
                Level(value="Very Low", ordinal=1),  # stored exactly (Patch 10)
            ],
        )
        rob2 = SchemeSpec(
            scheme_id="rob2",
            kind="RoB2",
            unit="study",
            levels=[
                Level(value="Low", ordinal=3),
                Level(value="Some concerns", ordinal=2),
                Level(value="High", ordinal=1),
            ],
        )
        robins = SchemeSpec(
            scheme_id="robins_i",
            kind="ROBINS-I",
            unit="study",
            levels=[
                Level(value="Low", ordinal=5),
                Level(value="Moderate", ordinal=4),
                Level(value="Serious", ordinal=3),
                Level(value="Critical", ordinal=2),
                # Patch 8: not a point on the risk scale.
                Level(value="No information", ordinal=None, missing_like=True),
            ],
        )
        return Config(
            rating=RatingConfig(
                primary_scheme=grade,
                secondary_schemes=[rob2, robins],
            )
        )

    def all_scheme_specs(self) -> list[SchemeSpec]:
        return [self.rating.primary_scheme, *self.rating.secondary_schemes]
