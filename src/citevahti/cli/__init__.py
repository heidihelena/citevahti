"""CiteVahti CLI (step 1): init the state layer, run startup probes, verify audit.

    citevahti init [--root DIR]
    citevahti probe [--root DIR]
    citevahti verify-audit [--root DIR]
"""

from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..rootcfg import default_root



from ._util import _DEMO_DIR, _parse_library, _fit_from_args, _emit_json, _print_support, _print_panel, _claim_report_text, _print_txn, _print_warehouse, _dedupe_breakdown, _report_intake, _subject, _safe, _print_write, _refs  # noqa: F401
from .commands import (  # noqa: F401
    _cmd_init,
    _cmd_probe,
    _cmd_verify_audit,
    _cmd_status,
    _cmd_preflight,
    _cmd_start,
    _cmd_doctor,
    _cmd_check_update,
    _cmd_run,
    _cmd_demo,
    _cmd_resume,
    _cmd_vocabulary,
    _cmd_timestamp,
    _cmd_agent_tools,
    _cmd_mcp_serve,
    _cmd_bib_sync,
    _cmd_extract,
    _cmd_claim_check,
    _cmd_claim_verify,
    _cmd_claim_add,
    _cmd_claim_untestable,
    _cmd_claim_propose_revision,
    _cmd_claim_accept_revision,
    _cmd_claim_reject_revision,
    _cmd_claim_list,
    _cmd_claim_link_candidates,
    _cmd_candidate_list,
    _cmd_support_start,
    _cmd_support_commit_human,
    _cmd_support_run_ai,
    _cmd_support_compare,
    _cmd_support_adjudicate,
    _cmd_support_show,
    _cmd_support_panel,
    _cmd_claim_decide,
    _cmd_test,
    _cmd_check_paragraph,
    _cmd_methods,
    _cmd_triage,
    _cmd_risk,
    _cmd_claim_report,
    _cmd_decision_list,
    _cmd_claim_commit,
    _cmd_cite_export,
    _cmd_txn_list,
    _cmd_txn_show,
    _cmd_txn_undo,
    _cmd_warehouse_status,
    _cmd_warehouse_emit,
    _cmd_warehouse_export,
    _cmd_warehouse_purge,
    _cmd_literature_search,
    _cmd_import_results,
    _cmd_snapshot,
    _cmd_corpus_diff,
    _cmd_surveillance_refresh,
    _cmd_map_bootstrap,
    _cmd_rating_start,
    _cmd_rating_commit_human,
    _cmd_rating_run_ai,
    _cmd_rating_compare,
    _cmd_rating_adjudicate,
    _cmd_assess,
    _cmd_license_scan,
    _cmd_retraction_scan,
    _cmd_prisma_ledger,
    _cmd_evidence_export,
    _cmd_agreement_report,
    _cmd_note_add,
    _cmd_tag_add,
    _cmd_tag_remove,
    _cmd_collection_add_item,
    _cmd_intake_push,
    _cmd_assessment_tag_mirror,
    _cmd_connect_zotero,
    _cmd_onboard,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citevahti")
    # Stable default ($CITEVAHTI_ROOT or home), NOT cwd — so `citevahti init` and the
    # desktop-launched MCP server resolve the SAME ledger regardless of working directory.
    parser.add_argument("--root", default=default_root(),
                        help="project root containing .citevahti/ (default: $CITEVAHTI_ROOT or your home folder)")
    parser.add_argument("--version", action="version", version=f"citevahti {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn, helptext in (
            ("init", _cmd_init,
             "create the project ledger (.citevahti/config.json) at --root — run this first"),
            ("probe", _cmd_probe, "probe Zotero / Better BibTeX / network capability"),
            ("verify-audit", _cmd_verify_audit,
             "recompute the hash-chained audit log and report whether it is intact (tamper check)"),
            ("status", _cmd_status, "machine-readable capability + connection report"),
            ("preflight", _cmd_preflight, "readiness snapshot for tooling (JSON-friendly)"),
            ("doctor", _cmd_doctor, "plain-language readiness check + version + the next thing to do"),
            ("check-update", _cmd_check_update,
             "check PyPI for a newer release (read-only, user-initiated; contacts pypi.org, never installs)"),
            ("vocabulary", _cmd_vocabulary, "print the verdicts / states / phases as JSON"),
            ("agent-tools", _cmd_agent_tools, "list the constrained agent tool surface")):
        p = sub.add_parser(name, help=helptext)
        p.set_defaults(func=fn)

    # start / run / resume all launch the workspace; run + resume add guided framing.
    for name, fn, helptext in (
        ("start", _cmd_start, "launch the panel + browser and serve MCP (ADR-0007)"),
        ("run", _cmd_run, "guided one command: init if needed, say what's next, open the panel"),
        ("resume", _cmd_resume, "resume where you left off — open the panel at the next pending step")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--port", type=int, default=8765, help="panel port (default 8765, loopback)")
        sp.add_argument("--no-browser", action="store_true",
                        help="don't open a browser window for the panel")
        sp.set_defaults(func=fn)

    dm = sub.add_parser("demo",
                        help="zero-setup 3-minute demo: synthetic ledger + panel (no Zotero/AI)")
    dm.add_argument("--dir", default=_DEMO_DIR,
                    help=f"where to build the demo ledger (default {_DEMO_DIR}; rebuilt each run)")
    dm.add_argument("--port", type=int, default=8765, help="panel port (default 8765, loopback)")
    dm.add_argument("--no-browser", action="store_true",
                    help="build the demo but don't open a browser")
    dm.set_defaults(func=_cmd_demo)

    ms = sub.add_parser(
        "mcp-serve", help="serve the constrained agent tools over MCP (stdio)",
        description="Serve CiteVahti's constrained agent tools to an MCP client (e.g. Claude "
                    "Desktop) over stdio. The ledger root is --root, else $CITEVAHTI_ROOT, else "
                    "your home folder. Usually launched by the client, not by hand.",
        epilog="example: citevahti --root ~/CiteVahti mcp-serve")
    ms.set_defaults(func=_cmd_mcp_serve)

    ts = sub.add_parser("timestamp",
                        help="opt-in cryptographic timestamp of the audit head (only the hash is sent)")
    ts.add_argument("--verify", metavar="PROOF_ID", default=None, help="verify a stored proof")
    ts.add_argument("--list", action="store_true", help="list recorded timestamp proofs")
    ts.add_argument("--fake", action="store_true",
                    help="local demo proof (no network, not third-party trusted)")
    ts.set_defaults(func=_cmd_timestamp)

    bs = sub.add_parser("bib-sync", help="scan sources, resolve citekeys, export bibliographies")
    bs.add_argument("--target", action="append", default=[],
                    help="file or directory to scan (repeatable)")
    bs.add_argument("--output-dir", default=None, help="where to write bibliography exports")
    bs.add_argument("--format", choices=["bibtex", "biblatex", "csl-json"], default="bibtex")
    bs.add_argument("--fail-on-orphans", action="store_true")
    bs.add_argument("--library", default="personal",
                    help="personal | group:<id> | all")
    bs.set_defaults(func=_cmd_bib_sync)

    ex = sub.add_parser("extract", help="assistive field extraction (read-only)")
    ex.add_argument("--citekey", default=None)
    ex.add_argument("--item-key", default=None)
    ex.add_argument("--field", action="append", default=[], help="field to extract (repeatable)")
    ex.add_argument("--require-passage", action="store_true")
    ex.add_argument("--library", default="personal", help="personal | group:<id> | all")
    ex.add_argument("--show-quotes", action="store_true",
                    help="print supporting quotes (off by default)")
    ex.set_defaults(func=_cmd_extract)

    cc = sub.add_parser("claim-check", help="deterministic lexical claim support (read-only)")
    cc.add_argument("--claim", required=True)
    cc.add_argument("--citekey", action="append", default=[], help="citekey (repeatable)")
    cc.add_argument("--require-page", action="store_true")
    cc.add_argument("--library", default="personal", help="personal | group:<id> | all")
    cc.add_argument("--show-quotes", action="store_true")
    cc.add_argument("--json", action="store_true",
                    help="emit the structured ClaimCheckResult as JSON — a stable, "
                         "machine-readable contract for callers integrating CiteVahti as a "
                         "citation verifier (see docs/INTEGRATION.md)")
    cc.set_defaults(func=_cmd_claim_check)

    cv = sub.add_parser("claim-verify",
                        help="check a claim against PROVIDED text — offline, no Zotero "
                             "(the integration seam for callers that have the source text)")
    cv.add_argument("--claim", required=True)
    cv.add_argument("--text", default=None, help="the source text inline")
    cv.add_argument("--text-file", default=None, help="read the source text from a file")
    cv.add_argument("--json", action="store_true",
                    help="emit the structured result as JSON (see docs/INTEGRATION.md). "
                         "With neither --text nor --text-file, the text is read from stdin.")
    cv.set_defaults(func=_cmd_claim_verify)

    from ..schemas.claim import CLAIM_TYPES, EXTRACTED_BY
    cla = sub.add_parser("claim-add", help="record a first-class manuscript claim (ADR-0001)")
    cla.add_argument("--text", required=True, help="the claim as asserted in the manuscript")
    cla.add_argument("--type", default="other", choices=list(CLAIM_TYPES))
    cla.add_argument("--location", default=None, help="manuscript location, e.g. 'Discussion ¶3'")
    cla.add_argument("--manuscript-id", default=None)
    cla.add_argument("--extracted-by", default="human", choices=list(EXTRACTED_BY))
    cla.add_argument("--extraction-model", default=None,
                     help="required when --extracted-by ai")
    cla.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    cla.set_defaults(func=_cmd_claim_add)

    cll = sub.add_parser("claim-list", help="list recorded claims (read-only)")
    cll.add_argument("--show-text", action="store_true", help="print full claim text")
    cll.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    cll.set_defaults(func=_cmd_claim_list)

    clu = sub.add_parser("claim-untestable",
                         help="mark a claim's source as out of indexed scope "
                              "(book/chapter/grey lit) — reported [u], not 'needs support'")
    clu.add_argument("claim_id")
    grp = clu.add_mutually_exclusive_group(required=True)
    grp.add_argument("--reason", help="why the source can't be auto-checked, "
                                      "e.g. '1992 monograph, not indexed'")
    grp.add_argument("--clear", action="store_true", help="remove the marker")
    clu.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    clu.set_defaults(func=_cmd_claim_untestable)

    cpr = sub.add_parser("claim-propose-revision",
                         help="attach a pending rewrite to review as a diff (applies nothing)")
    cpr.add_argument("--claim-id", required=True)
    cpr.add_argument("--text", required=True, help="the proposed new claim text")
    cpr.add_argument("--extracted-by", default="human", choices=list(EXTRACTED_BY))
    cpr.add_argument("--extraction-model", default=None, help="required when --extracted-by ai")
    cpr.set_defaults(func=_cmd_claim_propose_revision)

    car = sub.add_parser("claim-accept-revision",
                         help="apply a pending rewrite to the claim text (audited before/after)")
    car.add_argument("--claim-id", required=True)
    car.add_argument("--expected-text", default=None,
                     help="optional stale-diff guard; must match the pending revision")
    car.set_defaults(func=_cmd_claim_accept_revision)

    crr = sub.add_parser("claim-reject-revision",
                         help="discard a pending rewrite; the claim text is unchanged")
    crr.add_argument("--claim-id", required=True)
    crr.set_defaults(func=_cmd_claim_reject_revision)

    clc = sub.add_parser("claim-link-candidates",
                         help="link staged intake hits to a claim as candidates (ADR-0001)")
    clc.add_argument("--claim-id", required=True)
    clc.add_argument("--intake-batch-id", required=True)
    clc.add_argument("--record-id", action="append", default=[],
                     help="limit to specific intake record_ids (repeatable)")
    clc.add_argument("--json", action="store_true", help="emit the link result as JSON (for tooling)")
    clc.set_defaults(func=_cmd_claim_link_candidates)

    cdl = sub.add_parser("candidate-list", help="list a claim's candidate papers (read-only)")
    cdl.add_argument("--claim-id", required=True)
    cdl.add_argument("--show-text", action="store_true", help="print full titles")
    cdl.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    cdl.set_defaults(func=_cmd_candidate_list)

    from ..schemas.claim_support import SUPPORT_VALUES
    css = sub.add_parser("claim-support-start",
                         help="start a blinded claim-support rating for a (claim, candidate)")
    css.add_argument("--claim-id", required=True)
    css.add_argument("--candidate-id", required=True)
    css.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    css.set_defaults(func=_cmd_support_start)

    csh = sub.add_parser("claim-support-commit-human",
                         help="commit + lock the human claim-support value (with PICO fit)")
    csh.add_argument("--rating-id", required=True)
    csh.add_argument("--value", required=True, choices=list(SUPPORT_VALUES))
    for f in ("population", "intervention", "outcome", "claim"):
        csh.add_argument(f"--{f}-fit", type=int, choices=[0, 1, 2], default=None)
    csh.add_argument("--rationale", default=None)
    csh.add_argument("--committed-by", default="human")
    csh.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csh.set_defaults(func=_cmd_support_commit_human)

    csa = sub.add_parser("claim-support-run-ai",
                         help="blind advisory AI claim-support rating (needs a pinned model)")
    csa.add_argument("--rating-id", required=True)
    csa.add_argument("--task-type", default="assess")
    csa.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csa.set_defaults(func=_cmd_support_run_ai)

    csc = sub.add_parser("claim-support-compare", help="compare human vs AI claim support")
    csc.add_argument("--rating-id", required=True)
    csc.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csc.set_defaults(func=_cmd_support_compare)

    csj = sub.add_parser("claim-support-adjudicate",
                         help="human/panel adjudication of a discordant support rating")
    csj.add_argument("--rating-id", required=True)
    csj.add_argument("--final-value", required=True, choices=list(SUPPORT_VALUES))
    csj.add_argument("--rationale", required=True)
    csj.add_argument("--decider", default="human", choices=["human", "panel"])
    csj.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csj.set_defaults(func=_cmd_support_adjudicate)

    csw = sub.add_parser("claim-support-show", help="show a claim-support rating (read-only)")
    csw.add_argument("--rating-id", required=True)
    csw.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csw.set_defaults(func=_cmd_support_show)

    csp = sub.add_parser("claim-support-panel",
                         help="organized-panel 'X of N support' aggregate (ADR-0008, read-only)")
    csp.add_argument("--claim-id", required=True)
    csp.add_argument("--candidate-id", help="summarize one pair; omit for the whole claim")
    csp.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    csp.set_defaults(func=_cmd_support_panel)

    from ..schemas.decision import FINAL_DECISIONS
    cdc = sub.add_parser("claim-decide",
                         help="record the human-owned final decision for a (claim, candidate)")
    cdc.add_argument("--claim-id", required=True)
    cdc.add_argument("--candidate-id", required=True)
    cdc.add_argument("--decision", required=True, choices=list(FINAL_DECISIONS))
    cdc.add_argument("--reason", required=True, help="why this decision (human accountability)")
    cdc.add_argument("--rating-id", default=None,
                     help="the claim-support rating this decision rests on")
    cdc.add_argument("--decided-by", default="human")
    cdc.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    cdc.set_defaults(func=_cmd_claim_decide)

    dcl = sub.add_parser("decision-list", help="list a claim's final decisions (read-only)")
    dcl.add_argument("--claim-id", required=True)
    dcl.add_argument("--json", action="store_true", help="emit JSON (for scripting/CI)")
    dcl.set_defaults(func=_cmd_decision_list)

    crp = sub.add_parser("claim-report",
                         help="citation-integrity test results — the 4-state claim report (read-only)")
    crp.add_argument("--show-text", action="store_true", help="print full claim text")
    crp.add_argument("--format", choices=["text", "md", "test", "json"], default="text",
                     help="text summary (default), a Markdown editor report, the claim-test report, or JSON")
    crp.add_argument("--output", default=None, help="write the report to a file instead of stdout")
    crp.add_argument("--json", action="store_true", help="shorthand for --format json (the VS Code extension)")
    crp.set_defaults(func=_cmd_claim_report)

    # `report` — the claim-test report ("the manuscript is the code; each claim is a
    # test"). A friendly alias over claim-report defaulting to the test framing.
    rpt = sub.add_parser("report",
                         help="claim-test report — run the evidence tests over every claim (read-only)")
    rpt.add_argument("--format", choices=["test", "text", "md", "json"], default="test",
                     help="the claim-test report (default), text, Markdown, or JSON")
    rpt.add_argument("--show-text", action="store_true", help="print full claim text (text format)")
    rpt.add_argument("--output", default=None, help="write the report to a file instead of stdout")
    rpt.set_defaults(func=_cmd_claim_report)

    # `risk` — the Epistemic Risk Score: a derived, advisory /100 triage number over
    # the claim report (never a pass/fail gate). Always exits 0.
    rsk = sub.add_parser("risk",
                         help="Epistemic Risk Score — advisory /100 manuscript triage (read-only)")
    rsk.add_argument("--json", action="store_true", help="emit the full risk report as JSON")
    rsk.set_defaults(func=_cmd_risk)

    # `triage` — the friendly front door: the few claims worth attention, worst-first,
    # each with the reason + the next action. "Review these, not all of them."
    trg = sub.add_parser("triage",
                         help="the few claims worth your attention now, worst-first, with why + what to do")
    trg.add_argument("--json", action="store_true", help="emit the full triage report as JSON")
    trg.set_defaults(func=_cmd_triage)

    # `methods` — the submission-ready methods paragraph (auto-filled with this ledger's
    # numbers) + the PRISMA-style "how the literature was found" disclosure. Read-only.
    mth = sub.add_parser("methods",
                         help="submission-ready methods paragraph + PRISMA discovery disclosure (read-only)")
    mth.add_argument("--output", default=None, help="write to a file instead of stdout")
    mth.set_defaults(func=_cmd_methods)

    # `check-paragraph` — the everyday in-writing loop: paste a snippet, see which of its
    # sentences map to vetted claims, which need attention, and which are new/untracked.
    cp = sub.add_parser("check-paragraph",
                        help="paste a paragraph you just wrote → which claims are vetted / need you / new")
    cp.add_argument("--text", default=None, help="the paragraph text (else --path, else stdin)")
    cp.add_argument("--path", default=None, help="read the paragraph from a file")
    cp.add_argument("--json", action="store_true", help="emit the full result as JSON")
    cp.set_defaults(func=_cmd_check_paragraph)

    # `test` — run the manuscript "unit test" suite (each claim is a test case) and
    # exit non-zero on failures, so it can gate CI on a manuscript repo.
    tst = sub.add_parser("test",
                         help="run unit tests on the manuscript — pass/fail per claim; exits non-zero on failure")
    tst.add_argument("--online", action="store_true",
                     help="also verify citations are real and not retracted (network; slower)")
    tst.add_argument("--json", action="store_true", help="emit the suite result as JSON")
    tst.set_defaults(func=_cmd_test)

    ccm = sub.add_parser("claim-commit",
                         help="decision-gated Zotero write for an accepted decision (dry-run default)")
    ccm.add_argument("--decision-id", required=True)
    ccm.add_argument("--collection-key", default=None)
    ccm.add_argument("--library", default=None,
                     help="write target: personal | group:<id> (default: the configured library)")
    ccm.add_argument("--commit", action="store_true", help="actually write (default is dry-run)")
    ccm.add_argument("--confirm-token", default=None,
                     help="approval token from a prior preview (else the CLI previews first)")
    ccm.add_argument("--allow-unverified-dedupe", action="store_true",
                     help="override a dedupe_unverified refusal when Zotero search is unavailable")
    ccm.add_argument("--json", action="store_true", help="emit the diff/transaction as JSON (for tooling)")
    ccm.set_defaults(func=_cmd_claim_commit)

    ce = sub.add_parser("cite-export",
                        help="embed [@citekey] for accepted claims into the .md + write references.bib")
    ce.add_argument("--manuscript", required=True, help="path to the manuscript .md")
    ce.add_argument("--out", default=None,
                    help="write the annotated markdown here (default: <name>.cited.md)")
    ce.add_argument("--bib", default=None,
                    help="write the bibliography here (default: references.bib beside the manuscript)")
    ce.add_argument("--in-place", action="store_true",
                    help="overwrite the manuscript with the annotated version")
    ce.add_argument("--docx", action="store_true",
                    help="also produce a Word .docx with live citations (needs Pandoc on PATH)")
    ce.add_argument("--json", action="store_true", help="emit the full result as JSON (for tooling)")
    ce.set_defaults(func=_cmd_cite_export)

    txl = sub.add_parser("txn-list", help="list Zotero write transactions (read-only)")
    txl.set_defaults(func=_cmd_txn_list)

    txs = sub.add_parser("txn-show", help="show a write transaction (read-only)")
    txs.add_argument("--transaction-id", required=True)
    txs.set_defaults(func=_cmd_txn_show)

    txu = sub.add_parser("txn-undo", help="undo a committed write (deletes only what it created)")
    txu.add_argument("--transaction-id", required=True)
    txu.add_argument("--json", action="store_true", help="emit the transaction as JSON (for tooling)")
    txu.set_defaults(func=_cmd_txn_undo)

    whs = sub.add_parser("warehouse-status",
                         help="de-identified validation warehouse status (opt-in, default off)")
    whs.set_defaults(func=_cmd_warehouse_status)

    whe = sub.add_parser("warehouse-emit",
                         help="emit one de-identified validation record (no-op if disabled)")
    whe.add_argument("--claim-id", required=True)
    whe.add_argument("--candidate-id", required=True)
    whe.set_defaults(func=_cmd_warehouse_emit)

    whx = sub.add_parser("warehouse-export", help="export the de-identified validation records")
    whx.add_argument("--output", default=None)
    whx.set_defaults(func=_cmd_warehouse_export)

    whp = sub.add_parser("warehouse-purge",
                         help="erase the validation warehouse (consent withdrawal)")
    whp.set_defaults(func=_cmd_warehouse_purge)

    ls = sub.add_parser("literature-search",
                        help="run a user-supplied PubMed query and stage results (pre-decision)")
    ls.add_argument("--query", required=True, help="exact PubMed query (never rewritten)")
    ls.add_argument("--question-id", default=None)
    ls.add_argument("--max-results", type=int, default=20)
    ls.add_argument("--include-abstracts", action="store_true")
    ls.add_argument("--library", default="personal", help="personal | group:<id> | all")
    ls.add_argument("--json", action="store_true", help="emit batch_id + staged hits as JSON (for tooling)")
    ls.set_defaults(func=_cmd_literature_search)

    ir = sub.add_parser("import-results", help="stage RIS/CSV/BibTeX records (manual fallback)")
    ir.add_argument("--path", default=None)
    ir.add_argument("--text", default=None)
    ir.add_argument("--format", choices=["ris", "csv", "bibtex"], required=True)
    ir.add_argument("--question-id", default=None)
    ir.add_argument("--source-label", default=None)
    ir.add_argument("--library", default="personal", help="personal | group:<id> | all")
    ir.set_defaults(func=_cmd_import_results)

    sn = sub.add_parser("snapshot", help="capture a read-only corpus + evidence-map snapshot")
    sn.add_argument("--label", default=None)
    sn.add_argument("--include-fulltext-hashes", action="store_true")
    sn.add_argument("--library", default="personal", help="personal | group:<id> | all")
    sn.set_defaults(func=_cmd_snapshot)

    cd = sub.add_parser("corpus-diff", help="compare two snapshots (or snapshot vs current)")
    cd.add_argument("--from", required=True, dest="from_id")
    cd.add_argument("--to", default=None)
    cd.add_argument("--current", action="store_true", help="compare against the live corpus")
    cd.add_argument("--mark-stale", action="store_true")
    cd.add_argument("--library", default="personal", help="personal | group:<id> | all")
    cd.set_defaults(func=_cmd_corpus_diff)

    sr = sub.add_parser("surveillance-refresh",
                        help="re-run a saved PubMed query from its own last-run date")
    sr.add_argument("--query-id", required=True)
    sr.add_argument("--max-results", type=int, default=20)
    sr.add_argument("--library", default="personal", help="personal | group:<id> | all")
    sr.set_defaults(func=_cmd_surveillance_refresh)

    mb = sub.add_parser("map-bootstrap", help="seed proposed evidence-map nodes from a guideline")
    mb.add_argument("--guideline-path", required=True)
    mb.add_argument("--write", action="store_true", help="apply (default is dry-run)")
    mb.add_argument("--library", default="personal", help="personal | group:<id> | all")
    mb.set_defaults(func=_cmd_map_bootstrap)

    def _subject_args(p):
        p.add_argument("--outcome-id", default=None)
        p.add_argument("--study-id", default=None)
        p.add_argument("--domain-id", default=None)

    rs = sub.add_parser("rating-start", help="start a dual-rating record")
    rs.add_argument("--frame-id", required=True)
    rs.add_argument("--scheme-id", required=True)
    _subject_args(rs)
    rs.set_defaults(func=_cmd_rating_start)

    rch = sub.add_parser("rating-commit-human", help="commit a blind human rating (locks)")
    rch.add_argument("--rating-id", required=True)
    rch.add_argument("--value", required=True)
    rch.add_argument("--rationale", default=None)
    rch.add_argument("--committed-by", default="human")
    rch.set_defaults(func=_cmd_rating_commit_human)

    rra = sub.add_parser("rating-run-ai", help="run the blinded advisory AI rater")
    rra.add_argument("--rating-id", required=True)
    rra.add_argument("--task-type", required=True)
    rra.set_defaults(func=_cmd_rating_run_ai)

    rc = sub.add_parser("rating-compare", help="compare human vs AI rating")
    rc.add_argument("--rating-id", required=True)
    rc.set_defaults(func=_cmd_rating_compare)

    rad = sub.add_parser("rating-adjudicate", help="human/panel adjudication of a discordance")
    rad.add_argument("--rating-id", required=True)
    rad.add_argument("--final-value", required=True)
    rad.add_argument("--rationale", required=True)
    rad.add_argument("--decider", choices=["human", "panel"], default="human")
    rad.set_defaults(func=_cmd_rating_adjudicate)

    asp = sub.add_parser("assess", help="record a human-chosen controlled rating value")
    asp.add_argument("--frame-id", required=True)
    asp.add_argument("--scheme-id", required=True)
    _subject_args(asp)
    asp.add_argument("--value", required=True)
    asp.add_argument("--rationale", default=None)
    asp.add_argument("--dual-rating", action="store_true")
    asp.add_argument("--tag-mirror", action="store_true")
    asp.set_defaults(func=_cmd_assess)

    rsc = sub.add_parser("retraction-scan", help="DOI/PMID retraction scan (no title-only matching)")
    rsc.add_argument("--citekey", action="append", default=[])
    rsc.add_argument("--doi", action="append", default=[])
    rsc.add_argument("--pmid", action="append", default=[])
    rsc.add_argument("--mark-stale", action="store_true")
    rsc.set_defaults(func=_cmd_retraction_scan)

    lsc = sub.add_parser("license-scan",
                         help="fill each candidate's reuse rights (oa_status/license) from "
                              "OpenAlex — reports, never decides reusability")
    lsc.add_argument("--json", action="store_true", help="emit the result counts as JSON")
    lsc.set_defaults(func=_cmd_license_scan)

    pl = sub.add_parser("prisma-ledger", help="human-only PRISMA flow accounting")
    pl.add_argument("--question-id", required=True)
    pl.add_argument("--action", required=True,
                    choices=["init", "record_decision", "update_counts", "export"])
    pl.add_argument("--payload", default=None, help="JSON payload for the action")
    pl.set_defaults(func=_cmd_prisma_ledger)

    ee = sub.add_parser("evidence-export", help="export neutral evidence tables (read-only)")
    ee.add_argument("--format", action="append", default=[],
                    choices=["csv", "markdown", "csl-json"])
    ee.add_argument("--citekey", action="append", default=[])
    ee.add_argument("--node-id", action="append", default=[])
    ee.add_argument("--outcome-id", action="append", default=[], dest="outcome_id_sel")
    ee.add_argument("--recommendation-id", action="append", default=[])
    ee.add_argument("--include-provenance", action="store_true")
    ee.add_argument("--include-ai-values", action="store_true")
    ee.set_defaults(func=_cmd_evidence_export)

    ar = sub.add_parser("agreement-report", help="human-AI agreement metrics (read-only)")
    ar.add_argument("--metric", action="append", default=[],
                    choices=["raw_agreement", "cohen_kappa", "weighted_kappa", "adjudication_rate"])
    ar.add_argument("--format", action="append", default=[], choices=["json", "csv", "markdown"])
    ar.add_argument("--scheme-id", default=None)
    ar.add_argument("--task-type", default=None)
    ar.add_argument("--group-by", action="append", default=[])
    ar.set_defaults(func=_cmd_agreement_report)

    def _wb_common(p):
        p.add_argument("--library", default="personal", help="personal | group:<id> | all")
        p.add_argument("--confirm-token", default=None,
                       help="token from a dry-run preview; omit for dry-run")

    na = sub.add_parser("note-add", help="add a child note (dry-run by default)")
    na.add_argument("--target", required=True)
    na.add_argument("--title", required=True)
    na.add_argument("--markdown", required=True)
    na.add_argument("--show-body", action="store_true", help="echo the note body (off by default)")
    _wb_common(na)
    na.set_defaults(func=_cmd_note_add)

    taga = sub.add_parser("tag-add", help="add tags (dry-run by default)")
    taga.add_argument("--target", action="append", required=True)
    taga.add_argument("--tag", action="append", required=True)
    _wb_common(taga)
    taga.set_defaults(func=_cmd_tag_add)

    tagr = sub.add_parser("tag-remove", help="remove tags (dry-run by default)")
    tagr.add_argument("--target", action="append", required=True)
    tagr.add_argument("--tag", action="append", required=True)
    _wb_common(tagr)
    tagr.set_defaults(func=_cmd_tag_remove)

    cai = sub.add_parser("collection-add-item", help="add items to a collection (dry-run by default)")
    cai.add_argument("--collection-key", required=True)
    cai.add_argument("--target", action="append", required=True)
    _wb_common(cai)
    cai.set_defaults(func=_cmd_collection_add_item)

    ip = sub.add_parser("intake-push", help="push staged intake records as items (dry-run default)")
    ip.add_argument("--batch-id", required=True)
    ip.add_argument("--record-id", action="append", default=[])
    ip.add_argument("--collection-key", default=None)
    ip.add_argument("--allow-review-required", action="store_true",
                    help="override the block on writing from a review_required (flagged) batch")
    _wb_common(ip)
    ip.set_defaults(func=_cmd_intake_push)

    atm = sub.add_parser("assessment-tag-mirror", help="mirror a human/final assessment tag")
    atm.add_argument("--rating-id", default=None)
    atm.add_argument("--assessment-attachment-id", default=None)
    _wb_common(atm)
    atm.set_defaults(func=_cmd_assessment_tag_mirror)

    ob = sub.add_parser("onboard", help="securely capture email/IDs/collection + secret keys")
    ob.add_argument("--ncbi-email", default=None)
    ob.add_argument("--zotero-user-id", default=None)
    ob.add_argument("--zotero-library-id", default=None)
    ob.add_argument("--zotero-library-type", choices=["user", "group"], default="user")
    ob.add_argument("--collection-key", default=None, help="default collection (e.g. EUU)")
    ob.add_argument("--backend", choices=["system_keyring", "env"], default="system_keyring")
    ob.add_argument("--ncbi-key", action="store_true", help="also capture the NCBI API key")
    ob.add_argument("--no-zotero-key", action="store_true", help="do not capture a Zotero write key")
    ob.add_argument("--fullvahti-token", action="store_true",
                    help="also capture the FullVahti plugin's tag-write token (wires the local_addon backend)")
    ob.add_argument("--skip-validate", action="store_true",
                    help="skip live validation of keys before storing")
    ob.set_defaults(func=_cmd_onboard)

    cz = sub.add_parser("connect-zotero",
                        help="guided one-paste Zotero connection (opens a pre-filled key page)")
    cz.add_argument("--key", default=None, help="paste the key non-interactively (else prompted/hidden)")
    cz.add_argument("--name", default="CiteVahti", help="label for the key in Zotero")
    cz.add_argument("--groups", choices=["none", "read", "write"], default="none",
                    help="pre-select shared/group-library access (use 'write' for shared collections)")
    cz.add_argument("--no-open", action="store_true", help="don't open the browser automatically")
    cz.set_defaults(func=_cmd_connect_zotero)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
