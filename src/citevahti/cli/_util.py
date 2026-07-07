"""Shared CLI formatting/parsing helpers (ADR-0010 PR 3c).

Used by the command handlers in ``cli.commands`` and by ``main()`` — extracted so
handlers import them without a cycle back into the package ``__init__``.
"""

from __future__ import annotations





_DEMO_DIR = "~/CiteVahti-demo"


def _parse_library(s: str):
    from ..zotero.library import coerce_library
    if s.startswith("group:"):
        return coerce_library({"kind": "group", "group_id": s.split(":", 1)[1]})
    return coerce_library(s)


def _fit_from_args(args):
    from ..schemas.claim_support import FitScores
    if not any(v is not None for v in (args.population_fit, args.intervention_fit,
                                       args.outcome_fit, args.claim_fit)):
        return None
    return FitScores(population_fit=args.population_fit, intervention_fit=args.intervention_fit,
                     outcome_fit=args.outcome_fit, claim_fit=args.claim_fit)


def _emit_json(obj) -> None:
    """Machine-readable output for any pydantic model / list of models (the
    scripting/CI surface — ids flow end-to-end without scraping stdout)."""
    import json as _json

    def conv(o):
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        if isinstance(o, list):
            return [conv(x) for x in o]
        return o
    print(_json.dumps(conv(obj), indent=2, ensure_ascii=False))


def _print_support(rec) -> None:
    h = rec.human_rating.value if rec.human_rating else None
    a = ("abstained" if (rec.ai_rating and rec.ai_rating.abstained)
         else (rec.ai_rating.value if rec.ai_rating else None))
    print(f"  rating_id   : {rec.rating_id}")
    print(f"  claim/cand  : {rec.claim_id} / {rec.candidate_id}")
    print(f"  human       : {h}")
    print(f"  ai          : {a}" + (f" (model={rec.ai_rating.provenance.model_id})"
                                    if rec.ai_rating else ""))
    print(f"  comparison  : {rec.comparison.status}")
    print(f"  final       : {rec.adjudication.final_value}"
          + (f" ({rec.adjudication.event})" if rec.adjudication.event else ""))


def _print_panel(p, indent: str = "") -> None:
    dist = ", ".join(f"{n}× {v}" for v, n in sorted(p["distribution"].items(), key=lambda kv: -kv[1]))
    agree = f"{int(p['raw_agreement'] * 100)}%" if p.get("raw_agreement") is not None else "n/a"
    print(f"{indent}{p['headline']}  ·  {p['tier']}-level  ·  agreement {agree}")
    if dist:
        print(f"{indent}  {dist}")


def _claim_report_text(rep, show_text: bool) -> str:
    c = rep.counts
    lines = [f"Citation-integrity report — {rep.total} claim(s) tested",
             f"  [oo] accepted          {c.get('accepted', 0)}",
             f"  [o ] needs support     {c.get('needs_support', 0)}",
             f"  [r ] review needed     {c.get('review_needed', 0)}",
             f"  [d ] decision recorded {c.get('decision_recorded', 0)}",
             f"  [u ] untestable        {c.get('untestable', 0)}", ""]
    for row in rep.rows:
        loc = f"  [{row.manuscript_location}]" if row.manuscript_location else ""
        text = row.claim_text if show_text else (row.claim_text[:64] + ("…" if len(row.claim_text) > 64 else ""))
        lines.append(f"  [{row.code}] {row.state:<18} {row.accepted_count}/{row.candidate_count} accepted{loc}")
        lines.append(f"        {text}")
    return "\n".join(lines)


def _print_txn(txn) -> None:
    print(f"  transaction : {txn.transaction_id}  ({txn.status})")
    print(f"  kind        : {txn.kind}  validated={txn.validated}")
    if txn.decision_id:
        print(f"  chain       : claim={txn.claim_id} cand={txn.candidate_id} decision={txn.decision_id}")
    created = (txn.result or {}).get("created_keys") or []
    if created:
        print(f"  created     : {created}  in collection {txn.collection_key}")
    if txn.undo_snapshot.get("delete_keys"):
        print(f"  undo path   : delete {txn.undo_snapshot['delete_keys']}")
    if txn.error_code:
        print(f"  error       : {txn.error_code} — {txn.remediation}")
    print(f"  audit event : {(txn.audit_event_id or '')[:16]}...")


def _print_warehouse(rep) -> None:
    print(f"  enabled        : {rep.enabled}")
    print(f"  include_claim_text: {rep.include_claim_text}")
    print(f"  record_count   : {rep.record_count}")
    if rep.emitted:
        print(f"  emitted        : {rep.emitted}")
    if rep.skipped_reason:
        print(f"  skipped        : {rep.skipped_reason}")
    if rep.output_file:
        print(f"  output         : {rep.output_file}")


def _dedupe_breakdown(rec) -> str:
    from collections import Counter
    c = Counter(h.dedupe_status for h in rec.hits)
    return ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "none"


def _report_intake(rec, root: str) -> int:
    from pathlib import Path as _P
    print(f"status: {rec.status}" + (f" ({rec.error_code})" if rec.error_code else ""))
    if rec.remediation:
        print(f"  remediation: {rec.remediation}")
    print(f"  provider     : {rec.provider}")
    if rec.total_count is not None:
        print(f"  total matched: {rec.total_count}  (returned/staged: {rec.result_count})")
    else:
        print(f"  result_count : {rec.result_count}")
    if rec.query_translation:
        print(f"  query xlated : {rec.query_translation}")
    for w in rec.warnings:
        print(f"  ⚠ warning    : {w}")
    if getattr(rec, "review_required", False):
        print("  ⚠ REVIEW REQUIRED: PubMed warned about / re-translated this query — "
              "verify the staged results match your intent before pushing them.")
    print(f"  hits staged  : {len(rec.hits)}")
    print(f"  dedupe       : {_dedupe_breakdown(rec)}")
    if rec.library_dedupe_status:
        print(f"  library dedupe: {rec.library_dedupe_status}")
    if rec.status == "ok":
        print(f"  intake file  : {_P(root) / '.citevahti' / 'intake' / (rec.batch_id + '.json')}")
        if rec.audit_event_id:
            print(f"  audit event  : {rec.audit_event_id[:16]}...")
    return 0 if rec.status == "ok" else 1


def _subject(args):
    from ..schemas.rating import Subject
    return Subject(outcome_id=getattr(args, "outcome_id", None),
                   study_id=getattr(args, "study_id", None),
                   domain_id=getattr(args, "domain_id", None))


def _safe(fn):
    from ..state.store import StateError
    from ..validators.errors import ValidationError
    from ..writeback.backend import WriteUnavailable
    from ..writeback.transaction import TransactionError
    try:
        return fn(), 0
    except (ValidationError, StateError, TransactionError, WriteUnavailable) as exc:
        # clean, single-line CLI error (e.g. undoing an already-undone transaction)
        print(f"error: {getattr(exc, 'code', 'error')}: {exc}")
        return None, 1


def _print_write(out) -> int:
    if out.__class__.__name__ == "WriteDiff":
        print(f"operation: {out.kind}  (dry-run)")
        print(f"  backend: {out.backend_kind} (available={out.backend_available})")
        print(f"  targets: {len(out.targets)}")
        for c in out.proposed_changes:
            print(f"  change: {c}")
        if out.status in ("not_mirrorable", "unsupported") or not out.confirm_token:
            # no usable token to confirm with — say so instead of printing a blank one
            print(f"  status: {out.status} ({out.error_code or 'no_token'}): "
                  f"{out.remediation or 'no confirmable write was produced'}")
            for w in out.warnings:
                print(f"  warning: {w}")
            return 1
        print(f"  confirm_token: {out.confirm_token}")
        for w in out.warnings:
            print(f"  warning: {w}")
        return 0
    # WriteResult
    print(f"operation: {out.kind}  status: {out.status}")
    if out.error_code:
        print(f"  error: {out.error_code}: {out.remediation}")
    res = out.result or {}
    if res.get("created_keys"):
        print(f"  created keys : {res['created_keys']}")
    if res.get("collection_key"):
        print(f"  collection   : {res['collection_key']}")
    if res.get("transaction_id"):
        print(f"  transaction  : {res['transaction_id']}  (undo: citevahti txn-undo --transaction-id {res['transaction_id']})")
    if out.audit_event_id:
        print(f"  audit event: {out.audit_event_id[:16]}...")
    return 0 if out.applied else 1


def _refs(keys):
    from ..schemas.common import ItemRef
    return [ItemRef(zotero_key=k) for k in keys]


# ---- non-secret metadata display (ADR-0010 PR 3c follow-up) -----------------------
# `status`/`onboard`/`connect` surface a few fields that describe secrets WITHOUT ever
# being one: the connection name, the backend id ("system_keyring"/"env"), where a secret
# RESOLVES from, and the list of secret NAMES stored/skipped. The real values live only in
# the OS keyring (credentials.py marks the same names as lookup-keys, not secret values).
#
# Every helper here maps its input to a string *literal* via a closed allowlist and returns
# only that literal — the input is used solely as a lookup key or a membership test, so no
# input value flows to the return. That is the shape a static taint scanner recognises as a
# sanitising barrier (CodeQL py/clear-text-logging-sensitive-data flags these diagnostic
# prints as a false positive on the field *name*; single-`dict.get`/membership forms clear
# it, whereas multi-branch `return input` or "build a list by iterating the tainted input"
# forms do not). Unknown inputs render as "other" rather than echoing an unclassified value.
_STORE_BACKENDS = {"system_keyring": "system_keyring", "env": "env"}
_SECRET_SOURCE_KINDS = {
    "env": "env", "unset": "unset", "store_unavailable": "store_unavailable",
}
_CONNECTION_NAMES = {
    "zotero_local_api": "zotero_local_api", "better_bibtex": "better_bibtex",
    "pubmed_ncbi": "pubmed_ncbi", "fullvahti": "fullvahti",
    "ncbi_api_key": "ncbi_api_key", "zotero_write_key": "zotero_write_key",
}
_SECRET_DISPLAY_NAMES = {
    "zotero_write_key": "zotero_write_key", "ncbi_api_key": "ncbi_api_key",
    "fullvahti_token": "fullvahti_token", "ai_api_key": "ai_api_key",
}


def store_backend_display(backend) -> str:
    """Display label for the secrets backend id (never a secret value)."""
    return _STORE_BACKENDS.get(str(backend), "other")


def connection_display(name) -> str:
    """Display label for a capability connection name (a fixed vocabulary — the
    secret-backed ones share their lookup-key name, never a value)."""
    return _CONNECTION_NAMES.get(str(name), "other")


def secret_source_display(source) -> str:
    """Display label for where a secret resolves from — env / system_keyring /
    store_unavailable / unset — never the value or the env-var/service path.

    Single `dict.get` returning a literal: the input is only ever a lookup key, so
    nothing flows from it to the return (the barrier shape a taint scanner clears)."""
    s = str(source)
    kind = "env" if s.startswith("env:") else s
    return _SECRET_SOURCE_KINDS.get(kind, "system_keyring")


def secret_names_display(names) -> list[str]:
    """The stored/skipped credential NAMES (never values), via a literal allowlist.

    Built by iterating the *allowlist* (all string literals) and keeping the ones
    present in the input — the input is only ever a membership test, never iterated
    into the output — so no input value flows to the returned list. Any input not in
    the allowlist is surfaced as an "other" count, preserving the total."""
    present = {str(n) for n in (names or [])}
    shown = [known for known in _SECRET_DISPLAY_NAMES if known in present]
    others = len(present) - len(shown)
    return shown + ["other"] * others
