"""Characterization: the ``citevahti.tools`` public function surface is frozen.

ADR-0010 PR 0 — the safety net the god-file decomposition depends on. `tools.py` is a
thin facade; the plan is to split it into a `tools/` package with a re-export `__init__`
that keeps every ``from citevahti.tools import X`` working. This test is the contract that
split must preserve **exactly**: the same public callables, importable from the same place.

It is deliberately crude (a frozen name set), and that is the point — its job is to catch an
accidental rename, drop, or silent move during the refactor, not to check behaviour. A
*new* public tool fails the second test on purpose: add it to the freeze consciously so the
surface can't grow without review.

Offline: imports repo files only.
"""

from __future__ import annotations

import inspect

from citevahti import tools

# Every public tool callable importable as `from citevahti.tools import X` today (101).
# Do NOT edit to make a refactor pass — a diff here means the public surface changed.
FROZEN_TOOLS = {
    "zot_search", "zot_item", "zot_collections", "zot_attachments", "cite", "bib_sync",
    "extract", "claim_check", "literature_search", "resolve_dois", "resolve_dois_by_title",
    "backfill_candidate_dois", "recheck_library", "openalex_search", "semanticscholar_search",
    "scan_retractions", "scan_licenses", "zotero_locate", "claim_lexical_check",
    "zotero_evidence", "import_results", "snapshot", "corpus_diff", "surveillance_refresh",
    "map_bootstrap", "rating_start", "rating_commit_human", "rating_run_ai", "rating_compare",
    "rating_adjudicate", "assess", "retraction_scan", "prisma_ledger", "aggregate_ratings",
    "evidence_export", "agreement_report", "model_advisor", "getting_started", "note_add",
    "annotation_add", "item_add", "tag_add", "tag_remove", "collection_add_item",
    "intake_push", "assessment_tag_mirror", "onboard", "add_claim", "list_claims",
    "claim_mark_untestable", "zotero_new_key_url", "connect_zotero", "zotero_oauth_start",
    "zotero_oauth_finish", "propose_revision", "accept_revision", "reject_revision",
    "claim_bond_status", "link_candidates", "list_candidates", "unlink_candidate",
    "support_start", "support_commit_human", "support_panel", "support_run_ai",
    "support_compare", "support_adjudicate", "get_support_rating", "decide", "warehouse_status",
    "warehouse_emit", "warehouse_export", "methods_statement", "export_review_packet",
    "export_report_docx", "import_manuscript_docx", "claim_tests_prompt", "topic_screen_prompt",
    "warehouse_purge", "warehouse_configure", "atlas_contribution_preview", "atlas_revoke",
    "list_decisions", "commit_decision", "undo_transaction", "list_transactions",
    "get_transaction", "cite_export", "cite_export_manuscript", "pandoc_status", "claim_report",
    "triage", "evidence_map", "check_paragraph", "check_update", "draft_context", "chat",
    "run_manuscript_tests", "ai_config_get", "ai_config_set", "ai_local_models",
}


def test_every_frozen_tool_is_importable_and_callable():
    """The split must keep each name importable from citevahti.tools and callable."""
    lost = {n for n in FROZEN_TOOLS if not callable(getattr(tools, n, None))}
    assert not lost, f"citevahti.tools lost public callable(s): {sorted(lost)}"


def test_public_function_surface_has_not_grown_unnoticed():
    """No public function may appear in citevahti.tools that isn't in the freeze — a new
    tool (or one re-exported from a new submodule) must be added to FROZEN_TOOLS on purpose."""
    public = {
        name for name, obj in vars(tools).items()
        if not name.startswith("_")
        and inspect.isfunction(obj)
        and getattr(obj, "__module__", "").startswith("citevahti")
    }
    added = public - FROZEN_TOOLS
    assert not added, f"new public tool(s) not in the freeze (add them consciously): {sorted(added)}"
    dropped = FROZEN_TOOLS - public
    assert not dropped, f"frozen tool(s) no longer defined/re-exported in citevahti.tools: {sorted(dropped)}"
