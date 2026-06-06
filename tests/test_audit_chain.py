"""Hash-chained audit log: append, verify, tamper detection."""

import json

from citevahti.state import CiteVahtiStore
from citevahti.state.audit import AuditLog, GENESIS_HASH


def test_append_and_verify(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.append("a", {"x": 1})
    log.append("b", {"y": 2})
    entries = log.entries()
    assert [e.seq for e in entries] == [0, 1]
    assert entries[0].prev_hash == GENESIS_HASH
    assert entries[1].prev_hash == entries[0].hash
    assert log.verify() is True


def test_tampering_breaks_chain(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.append("a", {"x": 1})
    log.append("b", {"y": 2})
    rows = [json.loads(l) for l in log.path.read_text().splitlines()]
    rows[0]["payload"] = {"x": 999}  # retroactive edit
    log.path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert log.verify() is False


def test_store_mutations_are_audited(tmp_path, frame):
    store = CiteVahtiStore(tmp_path)
    store.init()
    store.save_frame(frame)
    events = [e.event for e in store.audit.entries()]
    assert "store.init" in events
    assert "frame.save" in events
    assert store.audit.verify() is True
