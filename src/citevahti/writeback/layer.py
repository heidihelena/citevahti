"""WriteLayer: dry-run preview + token-guarded apply over a single backend."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from .. import __version__
from ..schemas.common import Provenance
from ..schemas.writeback import WriteDiff, WriteOperation, WriteResult
from ..state.store import _atomic_write
from ..util import canonical_json, config_hash, sha256_hex, utc_now_iso
from .backend import WriteBackend, WriteUnavailable

_TOKEN_TTL_SECONDS = 3600


def _payload_hash(op: WriteOperation) -> str:
    # Binds EVERYTHING the confirmed write will use — including ``structured``, where
    # intake push keeps the full paper metadata (not in ``payload``). Without it, that
    # metadata could change between preview and commit and the token would still match,
    # so the committed write could differ from what the human approved.
    return sha256_hex(canonical_json({"kind": op.kind, "library": op.library,
                                      "targets": sorted(op.targets), "payload": op.payload,
                                      "structured": op.structured}))


class WriteLayer:
    def __init__(self, store, backend: WriteBackend, confirm_required: bool = True,
                 token_ttl: int = _TOKEN_TTL_SECONDS) -> None:
        self.store = store
        self.backend = backend
        self.confirm_required = confirm_required
        self.token_ttl = token_ttl

    def _pending_dir(self):
        return self.store.dir / "pending"

    def _provenance(self, op: WriteOperation) -> Provenance:
        return Provenance(tool="writeback", tool_version=__version__, ran_at=utc_now_iso(),
                          config_hash=config_hash({"kind": op.kind, "backend": self.backend.kind}),
                          sources=[{"kind": "writeback", "detail": self.backend.kind}])

    # ---- dry-run preview -------------------------------------------------
    def preview(self, op: WriteOperation) -> WriteDiff:
        supported = self._supports(op.kind)
        # Capability-honest: if the configured (available) backend cannot perform
        # this op kind, fail the preview EARLY -- no usable token is minted, so the
        # UI/CLI never offers a confirm that would later fail.
        if self.backend.available and not supported:
            return WriteDiff(
                kind=op.kind, library=op.library, targets=op.targets,
                proposed_changes=op.proposed_changes, structured=op.structured,
                confirm_token="", dry_run=True, backend_kind=self.backend.kind,
                backend_available=True, backend_supports_kind=False, status="unsupported",
                error_code="operation_unsupported",
                remediation=(f"The configured '{self.backend.kind}' backend does not support "
                             f"'{op.kind}'. Supported here: {', '.join(self._supported_kinds())}. "
                             "A confirmed write would fail."),
                warnings=["This operation is not supported by the configured backend."],
                provenance=self._provenance(op))

        phash = _payload_hash(op)
        nonce = uuid.uuid4().hex
        token = sha256_hex(phash + nonce)
        pending = {"token": token, "payload_hash": phash, "kind": op.kind,
                   "targets": op.targets, "created_at": utc_now_iso()}
        _atomic_write(self._pending_dir() / f"{token}.json", json.dumps(pending, indent=2))
        diff = WriteDiff(kind=op.kind, library=op.library, targets=op.targets,
                         proposed_changes=op.proposed_changes, structured=op.structured,
                         confirm_token=token, dry_run=True, backend_kind=self.backend.kind,
                         backend_available=self.backend.available,
                         backend_supports_kind=supported, provenance=self._provenance(op))
        if not self.backend.available:
            diff.warnings.append(
                "write backend is unavailable; this is a local preview only. A confirmed write "
                "would fail cleanly with write_layer_unavailable.")
        return diff

    # ---- capability helpers ---------------------------------------------
    def _supports(self, kind: str) -> bool:
        fn = getattr(self.backend, "supports", None)
        return bool(fn(kind)) if callable(fn) else True

    def _supported_kinds(self) -> list[str]:
        from .backend import ALL_WRITE_KINDS
        return [k for k in ALL_WRITE_KINDS if self._supports(k)] or ["(none)"]

    def _audit_failed(self, op: WriteOperation, code: str):
        try:
            return self.store.audit.append(
                "zotero.write.failed",
                {"kind": op.kind, "backend": self.backend.kind, "error_code": code,
                 "targets": len(op.targets)})
        except Exception:  # noqa: BLE001 (auditing a failure must never mask it)
            return None

    # ---- guarded apply ---------------------------------------------------
    def apply(self, op: WriteOperation, confirm_token: Optional[str]) -> WriteResult:
        prov = self._provenance(op)
        res = WriteResult(kind=op.kind, library=op.library, targets=op.targets,
                          backend_kind=self.backend.kind, provenance=prov)

        # ---- capability gate (fail fast, BEFORE the token gate) ----------
        # An op the backend can't perform, or an unconfigured backend, fails
        # immediately and the attempt is audited -- never a misleading token
        # dance that ends in a late failure, and never a silent fallback.
        if self.backend.available and not self._supports(op.kind):
            entry = self._audit_failed(op, "operation_unsupported")
            res.status = "failed"
            res.error_code = "operation_unsupported"
            res.remediation = (f"The configured '{self.backend.kind}' backend does not support "
                               f"'{op.kind}'. Supported here: {', '.join(self._supported_kinds())}.")
            res.audit_event_id = entry.hash if entry else None
            return res
        if not self.backend.available:
            entry = self._audit_failed(op, "write_layer_unavailable")
            res.status = "unavailable"
            res.error_code = "write_layer_unavailable"
            res.remediation = getattr(self.backend, "reason", "write backend unavailable")
            res.audit_event_id = entry.hash if entry else None
            return res

        # ---- token gate --------------------------------------------------
        if self.confirm_required and not confirm_token:
            return self._fail(res, "missing_confirm_token",
                              "A confirmation token from a dry-run preview is required to write.")

        pending_path = self._pending_dir() / f"{confirm_token}.json"
        if not pending_path.exists():
            return self._fail(res, "invalid_or_expired_token",
                              "No pending write matches this token; re-run the dry-run preview.")
        pending = json.loads(pending_path.read_text())

        # token is invalid if the payload changed since the preview
        if pending["payload_hash"] != _payload_hash(op):
            return self._fail(res, "payload_changed_token_invalid",
                              "The operation payload changed since the preview; re-preview to "
                              "get a fresh token.")
        if self._expired(pending["created_at"]):
            pending_path.unlink(missing_ok=True)
            return self._fail(res, "token_expired", "The confirmation token has expired.")

        try:
            details = self.backend.apply(op)
        except WriteUnavailable as exc:
            entry = self._audit_failed(op, "write_layer_unavailable")
            res.status = "unavailable"
            res.error_code = "write_layer_unavailable"
            res.remediation = str(exc)
            res.audit_event_id = entry.hash if entry else None
            return res

        pending_path.unlink(missing_ok=True)          # one-use token
        entry = self.store.audit.append(
            "zotero.write.applied",
            {"kind": op.kind, "backend": self.backend.kind, "targets": len(op.targets)})
        res.applied = True
        res.status = "applied"
        res.result = details
        res.audit_event_id = entry.hash
        return res

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _fail(res: WriteResult, code: str, remediation: str) -> WriteResult:
        res.applied = False
        res.status = "failed"
        res.error_code = code
        res.remediation = remediation
        return res

    def _expired(self, created_at: str) -> bool:
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - created).total_seconds() > self.token_ttl
