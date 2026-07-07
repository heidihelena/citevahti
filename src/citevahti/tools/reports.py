"""Read-only reporting views (ADR-0010 PR 1c — read-only group).

Derived views over the ledger for the panel and the researcher: the 4-state
citation-integrity report, the risk-first triage, the claim<->evidence map, the methods
paragraph, the model second-opinion advisor, and the draft-from-vetted-claims context.
Every one is read-only — it reads the ledger and returns data, mutating nothing, deciding
nothing, writing no file and no audit entry.

The file/audit-writing exports that live near these — ``evidence_export``,
``agreement_report``, ``export_review_packet``, ``export_report_docx``, ``cite_export`` —
stay in the facade for a later export-focused PR (ADR-0010 §3: read-only first).

Re-exported unchanged from ``citevahti.tools`` (frozen by tests/test_tools_public_api_stable.py).
"""

from __future__ import annotations

from typing import Optional

from ._common import _open_store

# final_decision (schemas/decision.py) -> the four verdict hues + unrated. Kept in one
# place so the panel map and any future export agree on the mapping.
_MAP_VERDICT = {"accept": "accept", "accepted_with_caution": "caution",
                "needs_second_review": "review", "reject": "reject"}


def claim_report(*, claim_ids: Optional[list] = None, root: Optional[str] = None):
    """Run citation-integrity tests over the project's claims (read-only 4-state report)."""
    from ..report import ClaimReportService
    return ClaimReportService(_open_store(root)).report(claim_ids=claim_ids)


def triage(*, root: Optional[str] = None):
    """Risk-first triage: the few claims worth your attention right now, worst-first,
    each with the reason and the next action. Read-only — the friendly front door to a
    review (review these, not all of them)."""
    from ..report import ClaimReportService
    from ..risk import triage as _triage
    report = ClaimReportService(_open_store(root)).report()
    return _triage(report)


def evidence_map(*, root: Optional[str] = None) -> dict:
    """Read-only claim<->evidence graph for the panel's Atlas map (and figure export).

    Nodes are claims and the *deduplicated* cited papers (one node per PMID/DOI, so a
    paper cited for several claims is a single shared node). Each edge is one
    (claim, candidate) pair carrying the human support rating, the **blinded** AI support
    (``"hidden"`` until the human has rated — the blinding rule is applied once, in
    ClaimReportService, never re-derived here), the final decision mapped to a verdict
    hue, and the retraction / staleness flags. A retracted paper is flagged independent
    of any rating. Mutates nothing; decides nothing."""
    from ..report import ClaimReportService

    store = _open_store(root)
    rep = ClaimReportService(store).report()

    def paper_key(pmid, doi, title):
        if pmid:
            return f"pmid:{pmid}"
        if doi:
            return f"doi:{str(doi).strip().lower()}"
        return f"title:{(title or '').strip().lower()[:80]}"

    papers: dict[str, dict] = {}
    edges: list[dict] = []
    claims: list[dict] = []
    for row in rep.rows:
        claims.append({"id": row.claim_id, "text": row.claim_text,
                       "type": row.claim_type, "location": row.manuscript_location,
                       "state": row.state, "code": row.code.strip(),
                       "untestable": bool(row.untestable_reason)})
        # candidate metadata (journal/year) for nicer paper labels; best-effort
        try:
            cands = {c.candidate_id: c for c in store.load_candidates(row.claim_id).candidates}
        except Exception:
            cands = {}
        for ev in row.evidence:
            pid = paper_key(ev.pmid, ev.doi, ev.title)
            node = papers.get(pid)
            if node is None:
                c = cands.get(ev.candidate_id)
                papers[pid] = {"id": pid, "title": ev.title, "pmid": ev.pmid, "doi": ev.doi,
                               "journal": getattr(c, "journal", None), "year": getattr(c, "year", None),
                               "retracted": bool(ev.retracted)}
            else:
                node["retracted"] = node["retracted"] or bool(ev.retracted)
                if not node.get("title") and ev.title:
                    node["title"] = ev.title
            edges.append({"claim_id": row.claim_id, "paper_id": pid,
                          "human_support": ev.human_support, "ai_support": ev.ai_support,
                          "decision": _MAP_VERDICT.get(ev.final_decision or "", "unrated"),
                          "final_decision": ev.final_decision, "agreement": ev.agreement,
                          "stale": bool(ev.stale)})

    prov = rep.provenance
    return {"claims": claims, "papers": list(papers.values()), "edges": edges,
            "counts": {"claims": len(claims), "papers": len(papers), "links": len(edges)},
            "generated_at": rep.generated_at, "warnings": rep.warnings,
            "retraction_source": getattr(prov, "retraction_source", None),
            "last_retraction_scan_at": getattr(prov, "last_retraction_scan_at", None)}


def methods_statement(*, root: Optional[str] = None) -> str:
    """The submission-ready methods paragraph for *this* ledger, as Markdown — the same
    text bundled into the review packet's ``methods.md``, but viewable directly so it can
    be read or pasted without unzipping. Includes the PRISMA-style 'how the literature was
    found' disclosure (whether an LLM was in the discovery loop). Read-only."""
    from ..report import build_methods_markdown
    return build_methods_markdown(_open_store(root))


def model_advisor(model_id: Optional[str] = None, *, root: Optional[str] = None):
    """Which identifiable AI model to trust as a second opinion, from the live
    complementary-catch scoreboard. Read-only, writes nothing. Ranks by validated
    catches (not agreement); pass ``model_id`` and, if it rates low, it suggests a
    better-evidenced alternative."""
    from ..export import AgreementReportService
    return AgreementReportService(_open_store(root)).advise_models(model_id)


def draft_context(*, root: Optional[str] = None) -> dict:
    """Read-only: the researcher's ACCEPTED claims, each with the citekey to cite it by —
    the user's own Better BibTeX key is resolved by cite-export; here we give the stable
    key minted from the paper's PMID/DOI (never an invented one). An accepted claim with
    no resolvable identifier is returned ``cited: False`` and flagged, so the draft skill
    can mark it as needing a source rather than fabricating one. Records nothing, writes
    nothing — it just gathers vetted claims to draft from."""
    from ..report import ClaimReportService
    from ..report.citation_export import mint_citekey
    from ..report.claim_report import _ACCEPTING

    rep = ClaimReportService(_open_store(root)).report()
    items = []
    for row in rep.rows:
        if row.state != "accepted":
            continue
        fresh = [e for e in row.evidence if e.final_decision in _ACCEPTING and not e.stale]
        if not fresh:
            items.append({"claim_text": row.claim_text, "citekey": None, "cited": False,
                          "reason": "the citation went stale (claim reworded) — re-accept to refresh"})
            continue
        ev = fresh[0]
        citekey = mint_citekey(ev.pmid, ev.doi)
        if not citekey:
            items.append({"claim_text": row.claim_text, "citekey": None, "cited": False,
                          "reason": "the accepted paper has no PMID or DOI to cite by"})
            continue
        items.append({"claim_text": row.claim_text, "citekey": citekey, "cited": True})
    return {"claims": items, "accepted": len(items),
            "cited": sum(1 for i in items if i["cited"])}
