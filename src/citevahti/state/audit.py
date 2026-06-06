"""Append-only, hash-chained audit log (``.citevahti/audit_log.jsonl``).

Every state mutation appends one line. Each entry's ``hash`` covers the previous
entry's hash, so any retroactive edit or deletion breaks the chain and is
detectable via :meth:`AuditLog.verify`.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from ..util import canonical_json, sha256_hex, utc_now_iso

try:
    import fcntl  # POSIX advisory file locks (macOS/Linux — the single-user target)
except ImportError:  # pragma: no cover — non-POSIX falls back to no cross-process lock
    fcntl = None  # type: ignore[assignment]

GENESIS_HASH = "0" * 64


@dataclass
class AuditEntry:
    seq: int
    ts: str
    event: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str

    @staticmethod
    def compute_hash(seq: int, ts: str, event: str, payload: dict[str, Any],
                     prev_hash: str) -> str:
        body = canonical_json(
            {"seq": seq, "ts": ts, "event": event, "payload": payload,
             "prev_hash": prev_hash}
        )
        return sha256_hex(body)


class AuditLog:
    """Hash-chained JSONL audit log."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextlib.contextmanager
    def _exclusive(self):
        """Serialize the read-compute-append across processes (chiefly the MCP
        server + the side panel writing the same ledger). The append reads the
        whole chain to compute ``seq``/``prev_hash``; without this lock two
        concurrent appends would race and corrupt the chain. POSIX ``flock`` on a
        sibling lock file; a no-op where ``fcntl`` is unavailable."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is None:  # pragma: no cover — non-POSIX
            yield
            return
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def entries(self) -> list[AuditEntry]:
        return [AuditEntry(**row) for row in self._read_raw()]

    def last_hash(self) -> str:
        rows = self._read_raw()
        return rows[-1]["hash"] if rows else GENESIS_HASH

    def append(self, event: str, payload: Optional[dict[str, Any]] = None) -> AuditEntry:
        payload = payload or {}
        with self._exclusive():
            rows = self._read_raw()
            seq = len(rows)
            prev_hash = rows[-1]["hash"] if rows else GENESIS_HASH
            ts = utc_now_iso()
            h = AuditEntry.compute_hash(seq, ts, event, payload, prev_hash)
            entry = AuditEntry(seq=seq, ts=ts, event=event, payload=payload,
                               prev_hash=prev_hash, hash=h)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def verify(self) -> bool:
        """Return True iff the chain is intact (seq order, prev links, hashes)."""
        prev_hash = GENESIS_HASH
        for i, row in enumerate(self._read_raw()):
            if row.get("seq") != i:
                return False
            if row.get("prev_hash") != prev_hash:
                return False
            expected = AuditEntry.compute_hash(
                row["seq"], row["ts"], row["event"], row["payload"], row["prev_hash"]
            )
            if row.get("hash") != expected:
                return False
            prev_hash = row["hash"]
        return True
