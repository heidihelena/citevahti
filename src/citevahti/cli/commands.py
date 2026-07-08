"""The CLI command handlers (ADR-0010 PR 3c) — logic, not routing.

Every ``_cmd_*`` handler, verbatim. ``cli/__init__.py`` keeps ``main()`` and the
argparse registration (routing); helpers come from ``._util`` (no cycle).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import __version__
from ..probe import HttpxClient, run_probes
from ..state import CiteVahtiStore



from ._util import (  # noqa: F401
    _DEMO_DIR, _parse_library, _fit_from_args, _emit_json, _print_support, _print_panel, _claim_report_text, _print_txn, _print_warehouse, _dedupe_breakdown, _report_intake, _subject, _safe, _print_write, _refs,
    connection_display, names_display, source_display, status_display,
    store_backend_display,
)


def _cmd_init(args) -> int:
    store = CiteVahtiStore(args.root)
    if store.exists():
        print(f"already initialized at {store.dir}")
        return 0
    cfg = store.init()
    print(f"initialized {store.dir}")
    print(f"  schema_version={cfg.schema_version}")
    print(f"  primary_scheme={cfg.rating.primary_scheme.scheme_id} "
          f"({cfg.rating.primary_scheme.kind})")
    pinned = cfg.ai_provenance.is_model_pinned()
    print(f"  ai model pinned: {pinned} "
          f"({cfg.ai_provenance.model_id})")
    return 0


def _cmd_probe(args) -> int:
    report = run_probes(HttpxClient())
    ok = True
    for name, r in report.results.items():
        mark = "OK " if r.available else "DOWN"
        line = f"[{mark}] {name}: {r.detail}"
        if r.version:
            line += f" (version={r.version})"
        elif r.version_status:
            line += f" (version_status={r.version_status})"
        print(line)
        if not r.available:
            ok = False
            if r.remediation:
                print(f"        remediation: {r.remediation}")
    return 0 if ok else 1


def _cmd_verify_audit(args) -> int:
    from ..claims.decisions import decision_inconsistency
    store = CiteVahtiStore(args.root)
    intact = store.audit.verify()
    print(f"audit chain intact: {intact} ({len(store.audit.entries())} entries)")
    # Materialized-state integrity: the hash chain only covers the LOG. Also check that
    # every decision FILE still agrees with its support rating — catches a decision edited
    # outside CiteVahti (e.g. final_decision flipped to 'accept') that the chain misses.
    bad = []
    for did in store.list_decisions():
        try:
            msg = decision_inconsistency(store, store.load_decision(did))
        except Exception as exc:  # noqa: BLE001
            msg = f"decision file unreadable: {exc}"
        if msg:
            bad.append((did, msg))
    if bad:
        print(f"decision state: {len(bad)} INCONSISTENT decision(s) — edited outside CiteVahti:")
        for did, msg in bad:
            print(f"  ⚠ {did}: {msg}")
        print("Reports and writes are blocked for affected claims until the ledger is repaired.")
    else:
        print("decision state: all decisions consistent with their ratings")
    return 0 if (intact and not bad) else 2


def _cmd_status(args) -> int:
    """Connection & Capabilities: the truth about what CiteVahti can do right now."""
    from ..capabilities import CapabilityStatusService
    from ..state import CiteVahtiStore as _Store

    store = _Store(args.root)
    if not store.exists():
        print(f"not initialized at {store.dir}; run `citevahti init` first")
        return 1
    rep = CapabilityStatusService(store, HttpxClient()).report()

    print("Connections")
    for c in rep.connections:
        mark = {"connected": "OK  ", "configured": "OK  ", "unavailable": "DOWN",
                "missing": "MISS", "store_unavailable": "WARN"}.get(c.status, "----")
        line = f"  [{mark}] {connection_display(c.name)}: {status_display(c.status)}"
        if c.version:
            line += f" (version={c.version})"
        if c.secret_source:
            line += f" [source={source_display(c.secret_source)}]"
        print(line)
        if c.remediation:
            print(f"         remediation: {c.remediation}")

    print(f"\nSecrets backend : {store_backend_display(rep.secrets_backend)}")
    print(f"Zotero user id  : {rep.zotero_user_id or '(unset)'}")

    print(f"\nWrite backend   : {rep.write_backend_kind} "
          f"(available={rep.write_backend_available})")
    if rep.write_backend_reason:
        print(f"  reason        : {rep.write_backend_reason}")
    print(f"  can write     : {', '.join(rep.supported_write_ops) or '(none)'}")
    print(f"  cannot write  : {', '.join(rep.unsupported_write_ops) or '(none)'}")

    print("\nPermissions")
    for k, v in rep.permissions.items():
        print(f"  {k}: {v}")
    for n in rep.notes:
        print(f"\nNote: {n}")
    return 0


def _cmd_preflight(args) -> int:
    """One read-only JSON snapshot for the guided 'Start manuscript review' flow.

    Never raises on a missing project or an unreachable backend — every field
    degrades to a safe default so the extension can render a checklist.
    """
    import json as _json
    from ..start import preflight_snapshot

    print(_json.dumps(preflight_snapshot(args.root, HttpxClient())))
    return 0


def _cmd_start(args) -> int:
    from ..start import start
    from ..panel import prefs
    root = args.root
    # avoid the empty-ledger trap: if this folder has no ledger, fall back to the
    # last-used root rather than serving a blank panel.
    if not prefs.has_ledger(root):
        fallback = prefs.recall_root()
        if fallback:
            print(f"note: {root} has no .citevahti ledger — using last-used root {fallback}",
                  file=sys.stderr)
            root = fallback
    return start(root, port=args.port, open_browser=not args.no_browser)


def _cmd_doctor(args) -> int:
    """Plain-language health check: what's ready, and the one next thing to do.

    The humane counterpart to `status`/`probe`/`preflight` — for the researcher who's
    never opened a terminal and just needs to be told what to fix."""
    from ..start import preflight_snapshot, readiness_lines

    snap = preflight_snapshot(args.root, HttpxClient())
    z, b = snap["zotero"], snap["better_bibtex"]
    print("CiteVahti — readiness check\n")
    print(f"  version        : citevahti {__version__}  (docs/CHANGELOG describe THIS version;"
          " if a guide shows other commands, it may be for a different release)")
    print(f"  ledger root    : {Path(args.root).expanduser()}")
    print(f"  project ledger : {'ready' if snap['project_initialized'] else 'not created'}")
    print(f"  Zotero         : {'reachable' if z['reachable'] else 'not detected'}"
          + (f" (v{z['version']})" if z.get('version') else ""))
    print(f"  Better BibTeX  : {'reachable' if b['reachable'] else 'not detected'}")
    print(f"  write-ready    : {'yes' if snap['zotero_write_ready'] else 'no (rating still works)'}")
    if snap.get("claims"):
        c = snap["claims"]
        need = c.get("needs_support", 0) + c.get("review_needed", 0)
        print(f"  claims         : {c['total']} ({need} still need you)")
    print("\nWhat to do next:")
    for line in readiness_lines(snap):
        print(f"  • {line}")
    return 0


def _cmd_check_update(args) -> int:
    """Check PyPI for a newer release. Read-only, user-initiated, never installs.

    Contacts pypi.org only when you run it (no launch-time or background phone-home), sends
    no data about you, and just tells you whether a newer CiteVahti is published. Pairs with
    `doctor`/`status`, which report the version you're RUNNING."""
    from ..update_check import check_update
    result = check_update()
    print(result["message"])
    # exit 0 whether up-to-date or update-available (both normal); only a FAILED check is
    # non-zero, so a script can tell "couldn't reach PyPI" from "checked successfully".
    return 0 if result["checked"] else 1


def _cmd_run(args) -> int:
    """Guided one command: create the ledger if needed, say what's next, open the panel.

    Resumable by construction — the ledger is the state, so re-running picks up exactly
    where you left off (same as `resume`)."""
    from ..start import preflight_snapshot, readiness_lines, start
    from ..state import CiteVahtiStore

    root = args.root
    store = CiteVahtiStore(root)
    if not store.exists():
        store.init()
        print(f"Created a new project ledger at {store.dir}.\n")
    for line in readiness_lines(preflight_snapshot(root, HttpxClient())):
        print(f"  • {line}")
    print("\nOpening the review panel — rate first; the AI's second rating stays hidden "
          "until you do.\n")
    return start(root, port=args.port, open_browser=not args.no_browser)


def _cmd_demo(args) -> int:
    """Zero-setup 3-minute demo: build a synthetic ledger and open the panel.

    No Zotero, no MCP, no AI, no network — just the real Rate → Reveal → Decide
    loop on an invented manuscript, so a first-timer can see the tool work."""
    import shutil
    from pathlib import Path

    from ..demo import build
    from ..start import start

    root = Path(args.dir).expanduser()
    is_default = args.dir == _DEMO_DIR
    if (root / ".citevahti").exists():
        if is_default:
            shutil.rmtree(root)            # our own disposable demo dir — rebuild fresh
        else:
            print(f"{root} already holds a ledger; pick an empty --dir for the demo.")
            return 1
    summary = build(root)
    print(f"Built a demo ledger at {summary['root']}")
    print(f"  manuscript: {summary['manuscript']}")
    print(f"  claims:     {summary['claims']} ({summary['decided']} decided, "
          f"{summary['pending']} awaiting your rating)\n")
    print("Opening the review panel — try claim #4 (it's staged for YOUR blind rating). "
          "Nothing here is real; delete the folder when you're done.\n")
    return start(str(root), port=args.port, open_browser=not args.no_browser)


def _cmd_resume(args) -> int:
    """Resume where you left off: name the next pending action, then open the panel
    (its 'what's next' banner routes you straight to the claim)."""
    from .. import workflow
    from ..start import start

    nxt = (workflow.project_status(args.root, HttpxClient()).get("next") or {})
    print(f"Resuming → {nxt.get('label', 'open the panel to continue.')}\n")
    return start(args.root, port=args.port, open_browser=not args.no_browser)


def _cmd_vocabulary(args) -> int:
    """The verdicts, states, and phases as JSON — one source every surface reads
    (so the VS Code extension stops hardcoding the verdict map)."""
    import json as _json

    from .. import workflow
    print(_json.dumps(workflow.vocabulary()))
    return 0


def _cmd_timestamp(args) -> int:
    """Opt-in cryptographic timestamp of the audit head (issue #42).

    Sends ONLY the audit-head hash to the configured RFC 3161 authority and stores the
    proof. Off unless `timestamp.provider` is configured; degrades honestly when offline.
    """
    from ..state import CiteVahtiStore
    from ..timestamp import (
        FakeTimestampProvider,
        TimestampService,
        TimestampUnavailable,
        provider_from_config,
    )
    from ..timestamp.service import provider_for_proof

    store = CiteVahtiStore(args.root)
    if not store.exists():
        print(f"not initialized at {store.dir}; run `citevahti init` first")
        return 1

    if args.list:
        ids = store.list_timestamps()
        if not ids:
            print("no timestamps recorded yet.")
            return 0
        for pid in ids:
            p = store.load_timestamp(pid)
            print(f"  {pid}  {p.gentime or '(no gentime)'}  {p.provider}  digest={p.digest_hex[:16]}…")
        return 0

    if args.verify:
        proof = store.load_timestamp(args.verify)
        svc = TimestampService(store, provider_for_proof(proof))
        res = svc.verify(args.verify)
        for k, v in res.items():
            print(f"  {k}: {v}")
        if res["verified"]:
            note = ("internally verified demo proof — NOT externally trusted"
                    if res["trust"] == "demo"
                    else "binding + chain verified; full TSA trust validation still pending")
            print(f"  => verified ({note})")
        else:
            print("  => NOT verified")
        return 0 if res["verified"] else 1

    # stamp the current head
    provider = FakeTimestampProvider() if args.fake else provider_from_config(store.load_config())
    if provider is None:
        print("timestamping is off. Set `timestamp.provider` (e.g. rfc3161 + a tsa_url) in "
              ".citevahti/config.json, or pass --fake for a local, non-trusted demo proof.")
        return 1
    try:
        proof = TimestampService(store, provider).stamp()
    except TimestampUnavailable as exc:
        print(f"could not timestamp (no proof written): {exc}")
        return 1
    print(f"timestamped audit head {proof.digest_hex[:16]}… → {proof.proof_id} "
          f"({proof.provider}, gentime {proof.gentime or 'n/a'})")
    return 0


def _cmd_agent_tools(args) -> int:
    """Show the constrained agent (MCP) surface and the capabilities it can never have."""
    from ..agent import ALLOWED_AGENT_TOOLS, FORBIDDEN_AGENT_CAPABILITIES, TOOLS
    print("CiteVahti agent surface (the ONLY tools an agent may call):")
    for name in ALLOWED_AGENT_TOOLS:
        lines = (TOOLS[name].__doc__ or "").strip().splitlines() if name in TOOLS else []
        print(f"  {name:24} {lines[0] if lines else ''}")
    print("\nCapabilities an agent can NEVER have:")
    for cap in FORBIDDEN_AGENT_CAPABILITIES:
        print(f"  ✕ {cap}")
    return 0


def _cmd_mcp_serve(args) -> int:
    from ..agent import mcp_server
    try:
        return mcp_server.main(["--root", args.root])
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1


def _cmd_bib_sync(args) -> int:
    from ..bibsync import BbtBibProvider, BibSyncService
    from ..state import CiteVahtiStore as _Store

    store = _Store(args.root)
    provider = BbtBibProvider(HttpxClient())
    report = BibSyncService(provider, store if store.exists() else None).run(
        args.target, output_dir=args.output_dir, export_format=args.format,
        fail_on_orphans=args.fail_on_orphans, library=args.library)
    print(f"status: {report.status}")
    if report.error_code:
        print(f"  error: {report.error_code}")
        if report.remediation:
            print(f"  remediation: {report.remediation}")
    print(f"  scanned files : {len(report.scanned_files)}")
    print(f"  unique keys   : {len(report.unique_citekeys)}")
    print(f"  resolved      : {len(report.resolved_citekeys)}")
    print(f"  orphans       : {len(report.orphan_citekeys)}"
          + (f"  {report.orphan_citekeys}" if report.orphan_citekeys else ""))
    print(f"  unused        : {len(report.unused_citekeys)}")
    print(f"  generated     : {len(report.generated_files)}")
    if report.audit_event_id:
        print(f"  audit event   : {report.audit_event_id[:16]}...")
    return 0 if report.status == "ok" else 1


def _cmd_extract(args) -> int:
    from .. import tools
    from ..schemas.common import ItemRef

    lib = _parse_library(args.library)
    subject = ItemRef(zotero_key=args.item_key or "", citekey=args.citekey, library=lib)
    res = tools.extract(subject, fields=args.field or None,
                        require_passage=args.require_passage, library=lib)
    print(f"status: {res.status}" + (f" ({res.error_code})" if res.error_code else ""))
    for field in res.fields:
        cands = res.candidates_by_field.get(field)
        if cands:
            print(f"  {field}: {cands[0].value}")
            if args.show_quotes:
                print(f"      quote: {cands[0].passage.quote[:160]}")
        else:
            print(f"  {field}: unverifiable")
    return 0 if res.status == "ok" else 1


def _cmd_claim_check(args) -> int:
    from .. import tools

    lib = _parse_library(args.library)
    res = tools.claim_check(args.claim, args.citekey or [], require_page=args.require_page,
                            library=lib)
    if getattr(args, "json", False):
        # stable machine-readable contract: the full ClaimCheckResult schema. Emits ONLY
        # JSON (no human lines) so a caller can parse stdout directly. Exit code still
        # distinguishes a usable result from "unverifiable".
        import json as _json
        print(_json.dumps(res.model_dump(), ensure_ascii=False, indent=2, default=str))
        return 0 if res.aggregate_status != "unverifiable" else 1
    print(f"aggregate: {res.aggregate_status}")
    for pc in res.per_citekey:
        line = f"  {pc.citekey}: {pc.status}"
        if pc.score is not None:
            line += f" (score={pc.score:.2f})"
        if pc.reason:
            line += f" [{pc.reason}]"
        print(line)
        if args.show_quotes:
            for p in pc.passages[:2]:
                print(f"      quote: {p.quote[:160]}")
    return 0 if res.aggregate_status != "unverifiable" else 1


def _cmd_claim_verify(args) -> int:
    """Check a claim against PROVIDED text — offline, no Zotero. The companion to
    claim-check for callers that already have the cited source's text (e.g. an external
    citation reviewer). Deterministic lexical overlap; never a verdict — see
    docs/INTEGRATION.md."""
    from .. import tools

    if args.text is not None:
        text = args.text
    elif args.text_file:
        text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()   # piped: `… | citevahti claim-verify --claim "…"`
    res = tools.claim_lexical_check(args.claim, text)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif not res.get("available"):
        print("unavailable: empty text or no content terms in the claim")
    else:
        print(f"status: {res['status']}  (coverage {res['coverage']})"
              + ("  ⚠ may contradict" if res.get("contradiction") else ""))
        if res.get("missing"):
            print(f"  missing terms: {', '.join(res['missing'])}")
    # exit 0 when we could check (terms_present/terms_missing are both valid results);
    # non-zero only when the check couldn't run at all.
    return 0 if res.get("available") else 1


def _cmd_claim_add(args) -> int:
    from .. import tools
    claim = tools.add_claim(
        args.text, args.type, manuscript_location=args.location,
        manuscript_id=args.manuscript_id, extracted_by=args.extracted_by,
        extraction_model=args.extraction_model, root=args.root)
    if getattr(args, "json", False):
        _emit_json(claim)
        return 0
    print(f"claim recorded: {claim.claim_id}")
    print(f"  type        : {claim.claim_type}")
    print(f"  extracted_by: {claim.extracted_by}"
          + (f" ({claim.extraction_model})" if claim.extraction_model else ""))
    if claim.manuscript_location:
        print(f"  location    : {claim.manuscript_location}")
    print(f"  audit event : {(claim.audit_event_id or '')[:16]}...")
    return 0


def _cmd_claim_untestable(args) -> int:
    from .. import tools
    reason = None if getattr(args, "clear", False) else args.reason
    claim = tools.claim_mark_untestable(args.claim_id, reason, root=args.root)
    if getattr(args, "json", False):
        _emit_json(claim)
        return 0
    if claim.untestable_reason:
        print(f"claim {claim.claim_id}: marked untestable (out of indexed scope)")
        print(f"  reason: {claim.untestable_reason}")
        print("  the report will show [u ] untestable — verify the claim against "
              "the source text directly")
    else:
        print(f"claim {claim.claim_id}: untestable marker cleared")
    return 0


def _cmd_claim_propose_revision(args) -> int:
    from .. import tools
    claim = tools.propose_revision(
        args.claim_id, args.text, extracted_by=args.extracted_by,
        extraction_model=args.extraction_model, root=args.root)
    by = claim.proposed_revision_by + (f" ({claim.proposed_revision_model})"
                                       if claim.proposed_revision_model else "")
    print(f"revision proposed for {claim.claim_id} by {by} — not applied")
    print(f"  current : {claim.claim_text}")
    print(f"  proposed: {claim.proposed_revision}")
    print("  accept with: claim-accept-revision / reject with: claim-reject-revision")
    return 0


def _cmd_claim_accept_revision(args) -> int:
    from .. import tools
    claim = tools.accept_revision(
        args.claim_id, expected_text=args.expected_text, root=args.root)
    print(f"revision applied to {claim.claim_id}")
    print(f"  claim now: {claim.claim_text}")
    return 0


def _cmd_claim_reject_revision(args) -> int:
    from .. import tools
    claim = tools.reject_revision(args.claim_id, root=args.root)
    print(f"revision rejected for {claim.claim_id}; claim unchanged")
    return 0


def _cmd_claim_list(args) -> int:
    from .. import tools
    claims = tools.list_claims(root=args.root)
    if getattr(args, "json", False):
        _emit_json(claims)
        return 0
    print(f"claims: {len(claims)}")
    for c in claims:
        loc = f"  [{c.manuscript_location}]" if c.manuscript_location else ""
        text = c.claim_text if args.show_text else (c.claim_text[:60] + ("…" if len(c.claim_text) > 60 else ""))
        print(f"  {c.claim_id}  ({c.claim_type}/{c.extracted_by}){loc}")
        print(f"      {text}")
    return 0


def _cmd_claim_link_candidates(args) -> int:
    from .. import tools
    rep = tools.link_candidates(args.claim_id, args.intake_batch_id,
                                record_ids=args.record_id or None, root=args.root)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({"claim_id": rep.claim_id, "intake_batch_id": rep.intake_batch_id,
                           "linked": rep.linked, "skipped_duplicates": rep.skipped_duplicates,
                           "total_candidates": rep.total_candidates}))
        return 0
    print(f"claim         : {rep.claim_id}")
    print(f"intake batch  : {rep.intake_batch_id}")
    print(f"  linked      : {rep.linked}")
    print(f"  skipped dup : {rep.skipped_duplicates}")
    print(f"  total cands : {rep.total_candidates}")
    print(f"  audit event : {(rep.audit_event_id or '')[:16]}...")
    return 0


def _cmd_candidate_list(args) -> int:
    from .. import tools
    cc = tools.list_candidates(args.claim_id, root=args.root)
    if getattr(args, "json", False):
        _emit_json(cc)
        return 0
    print(f"claim {cc.claim_id}: {len(cc.candidates)} candidate(s)")
    for c in cc.candidates:
        ids = " ".join(p for p in (f"pmid:{c.pmid}" if c.pmid else "",
                                   f"doi:{c.doi}" if c.doi else "") if p)
        rank = f"#{c.retrieval_rank}" if c.retrieval_rank is not None else ""
        zot = " [in-library]" if c.already_in_zotero else ""
        title = c.title if args.show_text else ((c.title or "")[:56] + ("…" if c.title and len(c.title) > 56 else ""))
        print(f"  {rank:>4} {ids}{zot}  cand={c.candidate_id}")
        print(f"       {title}")
        if c.retrieval_source:
            print(f"       via {c.retrieval_source} (why: {c.why_found})")
    return 0


def _cmd_support_start(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.support_start(args.claim_id, args.candidate_id, root=args.root))
    if rec:
        if getattr(args, "json", False):
            _emit_json(rec)
        else:
            print(f"claim-support rating started: {rec.rating_id}")
    return rc


def _cmd_support_commit_human(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.support_commit_human(
        args.rating_id, args.value, fit=_fit_from_args(args), rationale=args.rationale,
        committed_by=args.committed_by, root=args.root))
    if rec:
        _emit_json(rec) if getattr(args, "json", False) else _print_support(rec)
    return rc


def _cmd_support_run_ai(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.support_run_ai(args.rating_id, args.task_type, root=args.root))
    if rec:
        _emit_json(rec) if getattr(args, "json", False) else _print_support(rec)
    return rc


def _cmd_support_compare(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.support_compare(args.rating_id, root=args.root))
    if rec:
        _emit_json(rec) if getattr(args, "json", False) else _print_support(rec)
    return rc


def _cmd_support_adjudicate(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.support_adjudicate(
        args.rating_id, args.final_value, args.rationale, args.decider, root=args.root))
    if rec:
        _emit_json(rec) if getattr(args, "json", False) else _print_support(rec)
    return rc


def _cmd_support_show(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.get_support_rating(args.rating_id, root=args.root))
    if rec:
        _emit_json(rec) if getattr(args, "json", False) else _print_support(rec)
    return rc


def _cmd_support_panel(args) -> int:
    from .. import tools
    res, rc = _safe(lambda: tools.support_panel(
        args.claim_id, getattr(args, "candidate_id", None), root=args.root))
    if not res:
        return rc
    if getattr(args, "json", False):
        _emit_json(res)
        return rc
    if args.candidate_id:
        _print_panel(res)
    else:
        print(f"claim {res['claim_id']} — {res['tier']}-level (widest panel)")
        if not res["candidates"]:
            print("  (no human ratings yet — a panel needs ≥1 named rater per claim)")
        for p in res["candidates"]:
            print(f"  candidate {p['candidate_id']}:")
            _print_panel(p, indent="    ")
    return rc


def _cmd_claim_decide(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.decide(
        args.claim_id, args.candidate_id, args.decision, args.reason,
        rating_id=args.rating_id, decided_by=args.decided_by, root=args.root))
    if rec and getattr(args, "json", False):
        _emit_json(rec)
        return rc
    if rec:
        print(f"final decision : {rec.final_decision}")
        print(f"  decision_id  : {rec.decision_id}")
        print(f"  claim/cand   : {rec.claim_id} / {rec.candidate_id}")
        print(f"  support      : {rec.final_support_status}")
        print(f"  agreement    : {rec.agreement_status}")
        print(f"  decided_by   : {rec.decided_by}")
        print(f"  audit event  : {(rec.audit_event_id or '')[:16]}...")
        if rec.final_decision in ("accept", "accepted_with_caution"):
            print(f"  → review+write: citevahti claim-commit --decision-id {rec.decision_id} --commit"
                  "   (shows a preview and asks before writing)")
    return rc


def _cmd_test(args) -> int:
    """Run the manuscript unit-test suite — pass/fail per claim, exit non-zero on failure."""
    import json as _json

    from .. import tools
    from ..state import CiteVahtiStore as _Store

    store = _Store(args.root)
    if not store.exists():
        print(f"not initialized at {store.dir}; run `citevahti init` first")
        return 1
    suite = tools.run_manuscript_tests(root=args.root, online=getattr(args, "online", False))
    if getattr(args, "json", False):
        print(_json.dumps(suite, indent=2))
        return 1 if suite["failed"] else 0

    mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}
    for c in suite["claims"]:
        text = " ".join(c["claim_text"].split())          # collapse newlines for one-line output
        text = text if len(text) <= 70 else text[:67] + "…"
        print(f"  [{mark[c['status']]}] {text}")
        if c["status"] == "fail":
            for chk in c["checks"]:
                if chk["status"] == "fail":
                    print(f"         ✗ {chk['name']}: {chk['detail'] or 'failed'}")
    scope = "online (citations verified)" if suite["online"] else "offline (structural)"
    print(f"\n{suite['passed']} passed · {suite['failed']} failed · {suite['skipped']} skipped "
          f"of {suite['total']} claims — {scope}")
    # A swallowed online-check error means citation_real / not_retracted ran on stale
    # data — say so loudly and fail the run, so a degraded check is never read as green.
    online_errors = suite.get("online_errors") or []
    if online_errors:
        print("\n⚠ online checks could not complete — citation verification is INCOMPLETE:")
        for e in online_errors:
            print(f"    • {e}")
        print("  (citation_real / not_retracted may be stale; treat this run as inconclusive.)")
    if not suite["online"]:
        print("Tip: add --online to verify citations are real and not retracted.")
    return 1 if (suite["failed"] or online_errors) else 0


def _cmd_check_paragraph(args) -> int:
    """Check-a-paragraph — paste what you just wrote; see what's vetted / needs you / new."""
    from .. import tools

    text = args.text
    if not text and args.path:
        text = Path(args.path).expanduser().read_text(encoding="utf-8")
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not text:
        print("Paste a paragraph: --text \"…\", --path FILE, or pipe it via stdin.")
        return 1
    c, rc = _safe(lambda: tools.check_paragraph(text, root=args.root))
    if not c:
        return rc
    if getattr(args, "json", False):
        print(c.model_dump_json(indent=2))
        return 0
    print(f"{c.total} claim-like sentence(s): {c.reviewed} reviewed · "
          f"{c.attention} need attention · {c.new} new\n")
    icon = {"reviewed": "✓", "attention": "⚠", "new": "•"}
    for s in c.sentences:
        print(f"{icon.get(s.status, '?')} {s.text[:76]}")
        if s.status == "attention":
            print(f"     {s.reason}  →  {s.action}")
        elif s.status == "new":
            print("     new — not tracked yet; add it to check it.")
    return 0


def _cmd_methods(args) -> int:
    """Methods statement — the submission-ready paragraph + PRISMA discovery disclosure."""
    from .. import tools

    md, rc = _safe(lambda: tools.methods_statement(root=args.root))
    if md is None:
        return rc
    if args.output:
        Path(args.output).expanduser().write_text(md, encoding="utf-8")
        print(f"Wrote methods statement to {args.output}")
    else:
        print(md)
    return 0


def _cmd_triage(args) -> int:
    """Risk-first triage — the few claims worth your attention now, worst-first."""
    from .. import tools

    t = tools.triage(root=args.root)
    if getattr(args, "json", False):
        print(t.model_dump_json(indent=2))
        return 0
    if t.needs_attention == 0:
        print(f"Nothing needs you right now — {t.clean} claim(s) clean. "
              f"(Risk {t.score}/100, {t.band}.)")
        return 0
    print(f"{t.needs_attention} of {t.total} claim(s) worth your attention "
          f"({t.clean} clean · risk {t.score}/100, {t.band}). Worst first:\n")
    for i, it in enumerate(t.items, start=1):
        flag = "‼ " if it.fatal else ""
        print(f"{i}. {flag}{(it.claim_text or '')[:72]}")
        print(f"     why : {it.reason}")
        print(f"     do  : {it.action}\n")
    return 0


def _cmd_risk(args) -> int:
    """Epistemic Risk Score — derived, advisory manuscript triage (never a gate)."""
    from .. import tools
    from ..risk import score_report

    r = score_report(tools.claim_report(root=args.root))
    if getattr(args, "json", False):
        print(r.model_dump_json(indent=2))
        return 0
    print(f"Epistemic Risk Score: {r.score}/100  ({r.band}; range {r.score_low}–{r.score_high})")
    print(f"  {r.n_tested}/{r.n_testable} testable claims reviewed "
          f"(coverage {r.coverage:.0%}); {r.n_claims} claims total")
    s = r.subscores
    print(f"  unsupported {s.unsupported_share:.0%} · contradiction {s.contradiction_risk:.0%} · "
          f"retraction {s.retraction_exposure:.0%} · disagreement {s.disagreement_risk:.0%} · "
          f"weak-fit {s.fit_risk:.0%}")
    if r.top_contributors:
        print("  highest-risk claims:")
        for c in r.top_contributors[:5]:
            print(f"    [risk {c.risk:>4}] {(c.claim_text or '')[:64]}")
    for cav in r.caveats:
        print(f"  · {cav}")
    return 0   # advisory only — never a non-zero gate


def _cmd_claim_report(args) -> int:
    """Citation-integrity test results: the 4-state claim report."""
    from .. import tools
    rep = tools.claim_report(root=args.root)
    needs = rep.counts.get("needs_support", 0) + rep.counts.get("review_needed", 0)
    rc = 0 if needs == 0 else 1                       # CI-style: non-zero when attention needed
    fmt = "json" if getattr(args, "json", False) else getattr(args, "format", "text")
    if fmt == "json":
        out = rep.model_dump_json(indent=2)
    elif fmt == "md":
        from ..report import render_markdown
        out = render_markdown(rep)
    elif fmt == "test":
        from ..report import render_test_report
        out = render_test_report(rep)
    else:
        out = _claim_report_text(rep, getattr(args, "show_text", False))
    output = getattr(args, "output", None)
    if output:
        from pathlib import Path as _P
        _P(output).write_text(out, encoding="utf-8")
        print(f"wrote {fmt} report to {output} ({rep.total} claims)")
    else:
        print(out)
    return rc


def _cmd_decision_list(args) -> int:
    from .. import tools
    decisions = tools.list_decisions(args.claim_id, root=args.root)
    if getattr(args, "json", False):
        _emit_json(decisions)
        return 0
    print(f"claim {args.claim_id}: {len(decisions)} decision(s)")
    for d in decisions:
        print(f"  {d.final_decision:<22} support={d.final_support_status} "
              f"agree={d.agreement_status}  cand={d.candidate_id}")
        print(f"      decision_id={d.decision_id}"
              + (f"   → claim-commit --decision-id {d.decision_id}"
                 if d.final_decision in ("accept", "accepted_with_caution") else ""))
    return 0


def _cmd_claim_commit(args) -> int:
    import json as _json

    from .. import tools
    if args.commit:
        # PREVIEW FIRST, ALWAYS. A write needs an approval token from a preview.
        # If a token is supplied (--confirm-token), the user already saw the preview
        # (e.g. the VS Code modal). Otherwise the CLI shows the preview and requires
        # an EXPLICIT confirmation; non-interactive callers must pass the token they
        # saw, so neither a script nor an agent can one-call write unseen.
        token = getattr(args, "confirm_token", None)
        allow = getattr(args, "allow_unverified_dedupe", False)
        if not token:
            diff, rc = _safe(lambda: tools.commit_decision(
                args.decision_id, collection_key=args.collection_key, library=getattr(args, "library", None),
                dry_run=True, root=args.root))
            if not diff:
                return rc
            token = getattr(diff, "confirm_token", "") or ""
            if getattr(args, "json", False):
                # programmatic callers must replay the token explicitly (no auto-write)
                print(_json.dumps({"status": "preview_required",
                                   "error_code": "missing_confirm_token",
                                   "decision_id": args.decision_id, "confirm_token": token,
                                   "proposed_changes": list(diff.proposed_changes),
                                   "remediation": "re-run with --confirm-token <token> to write"},
                                  indent=2))
                return 1
            print(f"About to write to Zotero (decision {args.decision_id}):")
            for c in diff.proposed_changes:
                print(f"  • {c}")
            print(f"  backend     : {diff.backend_kind} (available={diff.backend_available})")
            for w in diff.warnings:
                print(f"  ⚠ {w}")
            if not diff.backend_available:
                print("  no write backend connected — run `citevahti connect-zotero` first.")
                return 1
            if not sys.stdin.isatty():
                print("\nrefusing to write without a visible confirmation. Re-run with the token "
                      "from this preview:")
                print(f"  citevahti claim-commit --decision-id {args.decision_id} --commit "
                      f"--confirm-token {token}")
                return 1
            try:
                resp = input("\nWrite the above to Zotero? [y/N]: ").strip().lower()
            except EOFError:
                resp = ""
            if resp not in ("y", "yes"):
                print("aborted — nothing was written.")
                return 1
        out, rc = _safe(lambda: tools.commit_decision(
            args.decision_id, collection_key=args.collection_key, library=getattr(args, "library", None),
            dry_run=False, confirm_token=token, allow_unverified_dedupe=allow, root=args.root))
        if out and getattr(args, "json", False):
            print(out.model_dump_json(indent=2))
            return 0 if out.status == "committed" else 1
        if out:
            print("validated write committed:" if out.status == "committed"
                  else f"write {out.status}:")
            _print_txn(out)
            if out.status != "committed":
                return 1
        return rc
    diff, rc = _safe(lambda: tools.commit_decision(
        args.decision_id, collection_key=args.collection_key, library=getattr(args, "library", None),
        dry_run=True, root=args.root))
    if diff and getattr(args, "json", False):
        print(diff.model_dump_json(indent=2))
        return rc
    if diff:
        print(f"dry-run preview (decision {args.decision_id}) — pass --commit to write:")
        for c in diff.proposed_changes:
            print(f"  • {c}")
        print(f"  backend     : {diff.backend_kind} (available={diff.backend_available})")
        for w in diff.warnings:
            print(f"  ⚠ {w}")
    return rc


def _cmd_cite_export(args) -> int:
    from .. import tools
    from ..report.citation_export import write_outputs
    res, rc = _safe(lambda: tools.cite_export(args.manuscript, root=args.root))
    if not res:
        return rc
    if getattr(args, "json", False):
        print(res.model_dump_json(indent=2))
        return 0
    if getattr(args, "docx", False) and not tools.pandoc_status().get("available"):
        print("fetching Pandoc (one-time, ~100 MB) to build the Word file…", file=sys.stderr)
    info = write_outputs(res, args.manuscript, out=args.out, bib=args.bib,
                         in_place=args.in_place, make_docx=getattr(args, "docx", False),
                         allow_pandoc_download=getattr(args, "docx", False))
    bbt = sum(1 for e in res.entries if e.key_source == "bbt")
    tail = f"; {bbt} matched your Zotero citekeys" if bbt else ""
    print(f"cited {res.injected} accepted claim(s); {res.skipped} skipped{tail}.")
    print(f"  manuscript   → {info['markdown_path']}")
    if info["bib_path"]:
        print(f"  bibliography → {info['bib_path']} ({res.bibtex.count('@article')} reference(s))")
    for w in res.warnings:
        print(f"  ⚠ {w}")
    st = info["docx_status"]
    if st == "ok":
        print(f"  Word         → {info['docx_path']}")
    elif st and st.startswith("pandoc_fetch_failed"):
        print("  ⚠ couldn't fetch Pandoc (offline?). The .md + .bib are ready; convert later with:")
        print(f"    pandoc {info['markdown_path']} --citeproc "
              f"--bibliography={info['bib_path']} -o manuscript.docx")
    elif st and st != "no_citations":
        print(f"  ⚠ Word export unavailable ({st}).")
    if not getattr(args, "docx", False) and info["bib_path"]:
        print("\nConvert to Word with live citations + a bibliography:")
        print(f"  pandoc {info['markdown_path']} --citeproc "
              f"--bibliography={info['bib_path']} -o manuscript.docx")
    return 0


def _cmd_txn_list(args) -> int:
    from .. import tools
    txns = tools.list_transactions(root=args.root)
    print(f"transactions: {len(txns)}")
    for t in txns:
        print(f"  {t.transaction_id}  {t.status:<10} {t.kind}  decision={t.decision_id}")
    return 0


def _cmd_txn_show(args) -> int:
    from .. import tools
    txn, rc = _safe(lambda: tools.get_transaction(args.transaction_id, root=args.root))
    if txn:
        _print_txn(txn)
    return rc


def _cmd_txn_undo(args) -> int:
    from .. import tools
    txn, rc = _safe(lambda: tools.undo_transaction(args.transaction_id, root=args.root))
    if txn and getattr(args, "json", False):
        print(txn.model_dump_json(indent=2))
        return 0 if txn.status == "undone" else 1
    if txn:
        print("undo result:")
        _print_txn(txn)
    return rc


def _cmd_warehouse_status(args) -> int:
    from .. import tools
    rep, rc = _safe(lambda: tools.warehouse_status(root=args.root))
    if rep:
        print("validation warehouse")
        _print_warehouse(rep)
    return rc


def _cmd_warehouse_emit(args) -> int:
    from .. import tools
    rep, rc = _safe(lambda: tools.warehouse_emit(args.claim_id, args.candidate_id, root=args.root))
    if rep:
        _print_warehouse(rep)
    return rc


def _cmd_warehouse_export(args) -> int:
    from .. import tools
    rep, rc = _safe(lambda: tools.warehouse_export(args.output, root=args.root))
    if rep:
        _print_warehouse(rep)
    return rc


def _cmd_warehouse_purge(args) -> int:
    from .. import tools
    rep, rc = _safe(lambda: tools.warehouse_purge(root=args.root))
    if rep:
        _print_warehouse(rep)
    return rc


def _cmd_literature_search(args) -> int:
    from .. import tools
    rec = tools.literature_search(
        args.query, question_id=args.question_id, max_results=args.max_results,
        include_abstracts=args.include_abstracts, library=_parse_library(args.library),
        root=args.root)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "status": rec.status, "error_code": rec.error_code, "remediation": rec.remediation,
            "batch_id": rec.batch_id, "provider": rec.provider,
            "result_count": rec.result_count, "total_count": rec.total_count,
            "review_required": bool(getattr(rec, "review_required", False)),
            "warnings": list(rec.warnings),
            "hits": [{"record_id": h.record_id, "pmid": h.pmid, "doi": h.doi,
                      "title": h.title, "dedupe_status": h.dedupe_status} for h in rec.hits]}))
        return 0 if rec.status == "ok" else 1
    return _report_intake(rec, args.root)


def _cmd_import_results(args) -> int:
    from .. import tools
    source = {"path": args.path} if args.path else {"text": args.text}
    rec = tools.import_results(source, args.format, question_id=args.question_id,
                               source_label=args.source_label,
                               library=_parse_library(args.library), root=args.root)
    return _report_intake(rec, args.root)


def _cmd_snapshot(args) -> int:
    from pathlib import Path as _P
    from .. import tools
    rec = tools.snapshot(label=args.label, library=_parse_library(args.library),
                         include_fulltext_hashes=args.include_fulltext_hashes, root=args.root)
    print(f"status: {rec.status}" + (f" ({rec.error_code})" if rec.error_code else ""))
    if rec.remediation:
        print(f"  remediation: {rec.remediation}")
    print(f"  snapshot_id     : {rec.snapshot_id}")
    print(f"  items           : {len(rec.items)}")
    print(f"  citekey coverage: {rec.citekey_coverage}")
    print(f"  zotero/bbt      : {rec.zotero_probe.version} / {rec.bbt_probe.version}")
    if rec.status == "ok":
        print(f"  file            : {_P(args.root) / '.citevahti' / 'snapshots' / (rec.snapshot_id + '.json')}")
        print(f"  audit event     : {(rec.audit_event_id or '')[:16]}...")
    return 0 if rec.status == "ok" else 1


def _cmd_corpus_diff(args) -> int:
    from .. import tools
    rep = tools.corpus_diff(args.from_id, to_snapshot_id=args.to,
                            compare_to_current=args.current, mark_stale=args.mark_stale,
                            library=_parse_library(args.library), root=args.root)
    print(f"status: {rep.status}" + (f" ({rep.error_code})" if rep.error_code else ""))
    if rep.remediation:
        print(f"  remediation: {rep.remediation}")
    print(f"  from -> to    : {rep.from_snapshot_id} -> {rep.to_snapshot_id}")
    print(f"  added         : {len(rep.added)}")
    print(f"  removed       : {len(rep.removed)}")
    print(f"  changed       : {len(rep.changed)}")
    print(f"  stale cands   : {len(rep.stale_candidates)}")
    print(f"  affected      : att={len(rep.affected.attachments)} ratings={len(rep.affected.ratings)} "
          f"rec={len(rep.affected.recommendation_nodes)} out={len(rep.affected.outcome_nodes)}")
    if rep.mark_stale:
        print(f"  stale flags   : {len(rep.stale_flags_added)} added")
        if rep.audit_event_id:
            print(f"  audit event   : {rep.audit_event_id[:16]}...")
    return 0 if rep.status == "ok" else 1


def _cmd_surveillance_refresh(args) -> int:
    from pathlib import Path as _P
    from .. import tools
    rec = tools.surveillance_refresh(args.query_id, max_results=args.max_results,
                                     library=_parse_library(args.library), root=args.root)
    print(f"status: {rec.status}" + (f" ({rec.error_code})" if rec.error_code else ""))
    if rec.remediation:
        print(f"  remediation: {rec.remediation}")
    print(f"  baseline_date : {rec.baseline_date}")
    print(f"  result_count  : {rec.result_count}")
    print(f"  hits staged   : {len(rec.hits)}")
    print(f"  dedupe        : {_dedupe_breakdown(rec)}")
    if rec.status == "ok":
        print(f"  intake file   : {_P(args.root) / '.citevahti' / 'intake' / (rec.batch_id + '.json')}")
        print(f"  audit event   : {(rec.audit_event_id or '')[:16]}...")
    return 0 if rec.status == "ok" else 1


def _cmd_map_bootstrap(args) -> int:
    from .. import tools
    rep = tools.map_bootstrap(args.guideline_path, library=_parse_library(args.library),
                              dry_run=not args.write, root=args.root)
    print(f"status: {rep.status}" + (f" ({rep.error_code})" if rep.error_code else ""))
    if rep.remediation:
        print(f"  remediation: {rep.remediation}")
    print(f"  sections      : {len(rep.sections)}")
    print(f"  resolved keys : {len(rep.resolved_citekeys)}")
    print(f"  orphan keys   : {len(rep.orphan_citekeys)}")
    print(f"  outcomes      : {len(rep.outcomes)}")
    print(f"  proposed nodes: {len(rep.proposed_nodes)}  links: {len(rep.proposed_links)}")
    print(f"  dry_run       : {rep.dry_run}   written: {rep.written}")
    if rep.written and rep.audit_event_id:
        print(f"  audit event   : {rep.audit_event_id[:16]}...")
    return 0 if rep.status == "ok" else 1


def _cmd_rating_start(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.rating_start(args.frame_id, args.scheme_id, _subject(args),
                                               root=args.root))
    if rec:
        print(f"rating_id: {rec.rating_id}  (frame={rec.frame_id} scheme={rec.scheme_id})")
    return rc


def _cmd_rating_commit_human(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.rating_commit_human(args.rating_id, args.value,
                                                      rationale=args.rationale,
                                                      committed_by=args.committed_by, root=args.root))
    if rec:
        print(f"committed (locked) human value for {rec.rating_id}")
    return rc


def _cmd_rating_run_ai(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.rating_run_ai(args.rating_id, args.task_type, root=args.root))
    if rec:
        ai = rec.ai_rating
        print(f"ai rating: {'abstained' if ai.abstained else ai.value} "
              f"(model={ai.provenance.model_id})")
    return rc


def _cmd_rating_compare(args) -> int:
    from .. import tools
    cmp, rc = _safe(lambda: tools.rating_compare(args.rating_id, root=args.root))
    if cmp:
        print(f"status: {cmp.status}  outcome: {cmp.outcome}  "
              f"needs_adjudication: {cmp.needs_adjudication}")
    return rc


def _cmd_rating_adjudicate(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.rating_adjudicate(args.rating_id, args.final_value,
                                                    args.rationale, args.decider, root=args.root))
    if rec:
        print(f"adjudicated final={rec.adjudication.final_value} by {rec.adjudication.decided_by}")
    return rc


def _cmd_assess(args) -> int:
    from .. import tools
    rec, rc = _safe(lambda: tools.assess(args.frame_id, args.scheme_id, _subject(args), args.value,
                                         rationale=args.rationale, dual_rating=args.dual_rating,
                                         tag_mirror=args.tag_mirror, root=args.root))
    if rec:
        print(f"status: {rec.status}  attachment: {rec.attachment_id}")
        if rec.rating_id:
            print(f"  rating_id: {rec.rating_id}")
        if rec.tag_mirror_status:
            print(f"  tag_mirror: {rec.tag_mirror_status}")
        if rec.stale_flags:
            print(f"  stale flags affecting subject: {len(rec.stale_flags)}")
    return rc


def _cmd_license_scan(args) -> int:
    """Fill candidates' reuse rights (oa_status/license) from OpenAlex. Reports, never
    decides — contacts OpenAlex (api.openalex.org) for each DOI/PMID."""
    from .. import tools
    rep = tools.scan_licenses(root=args.root)
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(rep, ensure_ascii=False))
    else:
        print(f"checked: {rep['checked']}  ·  filled: {rep['filled']}")
    return 0


def _cmd_retraction_scan(args) -> int:
    from .. import tools
    selection = {"citekeys": args.citekey, "dois": args.doi, "pmids": args.pmid}
    rep = tools.retraction_scan(selection, mark_stale=args.mark_stale, root=args.root)
    print(f"status: {rep.status}" + (f" ({rep.error_code})" if rep.error_code else ""))
    if rep.remediation:
        print(f"  remediation: {rep.remediation}")
    print(f"  scanned   : {rep.scanned_count}")
    print(f"  retracted : {len(rep.retracted)}")
    if rep.mark_stale:
        print(f"  flags     : retraction={len(rep.retraction_flags_added)} "
              f"stale={len(rep.staleness_flags_added)}")
    return 0 if rep.status == "ok" else 1


def _cmd_prisma_ledger(args) -> int:
    import json as _json
    from .. import tools
    payload = _json.loads(args.payload) if args.payload else None
    rec, rc = _safe(lambda: tools.prisma_ledger(args.question_id, args.action, payload,
                                                root=args.root))
    if rec:
        print(f"action: {args.action}  decisions: {len(rec.decisions)}  "
              f"ai_vote_refs: {len(rec.ai_vote_refs)}")
        if rec.counts:
            print(f"  counts: {rec.counts}")
        if rec.generated_files:
            for f in rec.generated_files:
                print(f"  wrote: {f}")
    return rc


def _cmd_evidence_export(args) -> int:
    from .. import tools
    selection = {"citekeys": args.citekey or None, "node_ids": args.node_id or None,
                 "outcome_ids": args.outcome_id_sel or None,
                 "recommendation_ids": args.recommendation_id or None}
    rep = tools.evidence_export(selection if any(selection.values()) else None,
                                formats=args.format or None,
                                include_provenance=args.include_provenance,
                                include_ai_values=args.include_ai_values, root=args.root)
    print(f"run: {rep.run_id}")
    print(f"  selected nodes/citekeys: {rep.selected_node_count} / {rep.selected_citekey_count}")
    print(f"  formats written        : {rep.formats_written}")
    for f in rep.output_files:
        print(f"  wrote: {f}")
    for w in rep.warnings:
        print(f"  warning: {w}")
    return 0


def _cmd_agreement_report(args) -> int:
    from .. import tools
    filters = {}
    if args.scheme_id:
        filters["scheme_id"] = args.scheme_id
    if args.task_type:
        filters["task_type"] = args.task_type
    if args.group_by:
        filters["group_by"] = args.group_by
    rep = tools.agreement_report(filters or None, metrics=args.metric or None,
                                 output_formats=args.format or None, root=args.root)
    print(f"run: {rep.run_id}")
    print(f"  comparable pairs: {rep.overall.comparable_pairs}  "
          f"agreements: {rep.overall.agreements}  disagreements: {rep.overall.disagreements}")
    print(f"  human_only: {rep.overall.human_only}  ai_abstained: {rep.overall.ai_abstained}  "
          f"pending_adjudication: {rep.overall.pending_adjudication}")
    print(f"  groups: {len(rep.groups)}  formats: {rep.formats_written}")
    for f in rep.output_files:
        print(f"  wrote: {f}")
    for w in rep.warnings:
        print(f"  warning: {w}")
    return 0


def _cmd_note_add(args) -> int:
    from .. import tools
    if args.show_body:
        print(f"  (note body, {len(args.markdown)} chars): {args.markdown}")
    out = tools.note_add(_refs([args.target])[0], args.title, args.markdown,
                         library=_parse_library(args.library), dry_run=not args.confirm_token,
                         confirm_token=args.confirm_token, root=args.root)
    return _print_write(out)


def _cmd_tag_add(args) -> int:
    from .. import tools
    out = tools.tag_add(_refs(args.target), args.tag, library=_parse_library(args.library),
                        dry_run=not args.confirm_token, confirm_token=args.confirm_token, root=args.root)
    return _print_write(out)


def _cmd_tag_remove(args) -> int:
    from .. import tools
    out = tools.tag_remove(_refs(args.target), args.tag, library=_parse_library(args.library),
                           dry_run=not args.confirm_token, confirm_token=args.confirm_token,
                           root=args.root)
    return _print_write(out)


def _cmd_collection_add_item(args) -> int:
    from .. import tools
    out = tools.collection_add_item(args.collection_key, _refs(args.target),
                                    library=_parse_library(args.library),
                                    dry_run=not args.confirm_token, confirm_token=args.confirm_token,
                                    root=args.root)
    return _print_write(out)


def _cmd_intake_push(args) -> int:
    from .. import tools
    out = tools.intake_push(args.batch_id, record_ids=args.record_id or None,
                            collection_key=args.collection_key,
                            library=_parse_library(args.library), dry_run=not args.confirm_token,
                            confirm_token=args.confirm_token,
                            allow_review_required=getattr(args, "allow_review_required", False),
                            root=args.root)
    return _print_write(out)


def _cmd_assessment_tag_mirror(args) -> int:
    from .. import tools
    out = tools.assessment_tag_mirror(rating_id=args.rating_id,
                                      assessment_attachment_id=args.assessment_attachment_id,
                                      dry_run=not args.confirm_token, confirm_token=args.confirm_token,
                                      root=args.root)
    return _print_write(out)


def _cmd_connect_zotero(args) -> int:
    """Guided one-paste Zotero connection (ADR-0005): open pre-filled key page, paste, store."""
    import getpass
    import os
    import sys

    from .. import tools
    from ..zotero import ZoteroConnectError

    url = tools.zotero_new_key_url(args.name, groups=args.groups)
    print("Connect CiteVahti to Zotero (reads are keyless; this enables guarded write-back):")
    grp = " + group-library access" if args.groups in ("read", "write") else ""
    print(f"  1. Open this page (it pre-fills the name + personal write permission{grp}):\n     {url}")
    if args.groups == "none":
        print("     (writing to a SHARED/GROUP library? re-run with --groups write, or tick the "
              "group on the page.)")
    print("  2. Click 'Save Key', then copy the key it shows.")
    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(url)
            print("     (opened in your browser)")
        except Exception:  # noqa: BLE001
            pass

    key = args.key or os.environ.get("CITEVAHTI_ZOTERO_WRITE_KEY")
    if not key:
        if not sys.stdin.isatty():
            print("error: no key provided. Pass --key, set $CITEVAHTI_ZOTERO_WRITE_KEY, or run interactively.")
            return 1
        key = getpass.getpass("  3. Paste the key (hidden, not echoed): ").strip()
    if not key:
        print("error: no key entered.")
        return 1

    try:
        rep = tools.connect_zotero(key, root=args.root)
    except ZoteroConnectError as exc:
        print(f"could not connect ({exc.code}): {exc.message}")
        return 1
    who = rep.get("username") or "your account"
    print(f"\n✓ Connected to Zotero as {who} (user {rep['user_id']}).")
    print(f"  personal library write : {'yes' if rep.get('personal_write') else 'NO'}")
    gt, gw = rep.get("groups_total", 0), rep.get("groups_write", 0)
    if gt:
        print(f"  group libraries        : {gt} on the key, {gw} writable")
    else:
        print("  group libraries        : none on this key "
              "(re-run with --groups write if you cite from a shared library)")
    print(f"  key storage            : {store_backend_display(rep['secrets_backend'])} (never written to config)")
    print(f"  {rep['note']}")
    return 0


def _cmd_onboard(args) -> int:
    import getpass
    import os
    import sys

    from .. import tools

    def get_secret(env_name: str, label: str, want: bool):
        if not want:
            return None
        v = os.environ.get(env_name)
        if v:
            print(f"  {label}: using ${env_name} (runtime injection)")
            return v
        if sys.stdin.isatty():
            return getpass.getpass(f"  {label} (input hidden, not echoed): ") or None
        print(f"  {label}: not provided (set ${env_name} or run interactively) — skipped")
        return None

    print("Onboarding (secrets never printed, never written to config):")
    zkey = get_secret("CITEVAHTI_ZOTERO_WRITE_KEY", "Zotero write key", not args.no_zotero_key)
    nkey = get_secret("CITEVAHTI_NCBI_API_KEY", "NCBI API key", args.ncbi_key)
    fvtoken = get_secret("CITEVAHTI_FULLVAHTI_TOKEN", "FullVahti plugin token",
                         getattr(args, "fullvahti_token", False))
    rep = tools.onboard(
        root=args.root, ncbi_email=args.ncbi_email, zotero_user_id=args.zotero_user_id,
        zotero_library_id=args.zotero_library_id, zotero_library_type=args.zotero_library_type,
        default_collection_key=args.collection_key, zotero_write_key=zkey, ncbi_api_key=nkey,
        fullvahti_token=fvtoken, secrets_backend=args.backend, validate=not args.skip_validate)
    print(f"secrets_backend : {store_backend_display(rep.secrets_backend)}")
    print(f"config updated  : {sorted(set(rep.config_updated))}")
    print(f"secrets stored  : {names_display(rep.secrets_stored) or '(none)'}")  # names only
    if rep.secrets_skipped:
        print(f"secrets skipped : {names_display(rep.secrets_skipped)}")
    if rep.validations:
        print(f"validations     : {rep.validations}")
    for w in rep.warnings:
        print(f"  warning: {w}")
    return 0
