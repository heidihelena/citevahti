"""The audit log is safe under concurrent appends (ADR-0007 v1 hardening).

The MCP server and the side panel write the same ``.citevahti/`` ledger. Each
``append`` reads the whole hash chain to compute ``seq``/``prev_hash`` and then
writes — a read-modify-write that two processes can race. An inter-process file
lock serializes it so the tamper-evident chain stays intact.
"""

import threading

from citevahti.state.audit import AuditLog


def test_concurrent_appends_keep_the_chain_intact(tmp_path):
    log = AuditLog(tmp_path / ".citevahti" / "audit_log.jsonl")
    n = 50
    barrier = threading.Barrier(n)        # release all writers at once → maximal contention
    errors = []

    def worker(i):
        try:
            barrier.wait()
            log.append("concurrent.event", {"i": i})
        except Exception as e:            # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert log.verify() is True                      # chain intact (no broken prev links)
    seqs = [e.seq for e in log.entries()]
    assert seqs == list(range(n))                    # contiguous + unique: nothing lost or duplicated


def test_single_append_still_returns_entry(tmp_path):
    log = AuditLog(tmp_path / "proj" / "audit_log.jsonl")
    entry = log.append("x", {"k": 1})
    assert entry.seq == 0 and log.verify() is True
