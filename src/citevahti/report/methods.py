"""Submission-ready methods statement — the REPORTING.md paragraph, auto-filled.

The fill-in-the-blanks methods paragraph in docs/REPORTING.md describes CiteVahti's
blinded human → AI → adjudication workflow. This fills it with *this* ledger's real
numbers so a review packet ships paste-ready text for a manuscript's methods section.

Honest by construction: unpinned model provenance and the absence of dual-rated
pairs are stated plainly (``unset`` / ``n/a``), never invented — the same discipline
as the rest of the reporting surface.
"""

from __future__ import annotations

from .. import __version__

# Mirrors the blockquote in docs/REPORTING.md. Kept here (not read from docs/) so the
# packet can be built from an installed wheel where docs/ is not present.
_TEMPLATE = (
    "Citation–evidence support was assessed claim by claim using CiteVahti {version} "
    "(Vahtian; Apache-2.0), which records a blinded dual-rating workflow: for each "
    "claim–candidate pair, a human rater first recorded a support rating (scale: "
    "directly_supports / partially_supports / does_not_support / contradicts / unclear) "
    "while the AI second opinion was withheld; an AI rater ({provider}, model "
    "{model_id}, snapshot {snapshot}, prompt template {prompt_version}) independently "
    "rated the same pair without access to the human value. Rating order ({blinding_mode}) "
    "and timestamps were recorded in a hash-chained audit log. Of {n_pairs} comparable "
    "human–AI pairs, {n_agree} were concordant and {n_disagree} discordant (raw "
    "agreement {raw_agreement}; Cohen's κ {kappa}). AI abstentions ({n_abstain}) were "
    "excluded from the agreement denominator. Every discordance was resolved by human "
    "adjudication with a recorded rationale; AI values were advisory only and never set "
    "the recorded final value. CiteVahti checks citation support, not the truth of the "
    "underlying claims."
)

def _shown(value: str, *, unset_hint: str) -> str:
    """The value, or an explicit ``(unset — …)`` marker — never a blank or a sentinel."""
    if value is None or str(value).startswith("PENDING") or str(value) in ("", "unset"):
        return f"(unset — {unset_hint})"
    return str(value)


def _kappa_str(report) -> str:
    for grp in report.groups:
        ck = grp.metrics.get("cohen_kappa")
        if isinstance(ck, dict) and ck.get("value") is not None and not ck.get("error"):
            return f"{ck['value']:.3f}"
    return "n/a (insufficient dual-rated pairs, or mixed schemes — see the agreement report)"


def _discovery_stats(store) -> dict:
    """What the ledger shows about how candidates were *found* — the identification
    step a systematic review must disclose. Counts AI-proposed claims, staged
    candidate papers, and the search batches that produced them."""
    from ..state import StateError

    claims = store.list_claims()
    ai_claims = 0
    model = None
    candidates = 0
    for cid in claims:
        try:
            c = store.load_claim(cid)
        except StateError:
            continue
        if getattr(c, "extracted_by", "human") == "ai":
            ai_claims += 1
            model = model or getattr(c, "extraction_model", None)
        try:
            candidates += len(store.load_candidates(cid).candidates)
        except StateError:
            pass
    return {"n_claims": len(claims), "ai_claims": ai_claims,
            "candidates": candidates, "searches": len(store.list_intake()),
            "model": model}


def _basis_stats(store) -> dict:
    """How was support actually assessed — against a located full-text passage, or the
    abstract the rater saw? A rating that carries a quoted passage (attachment + char
    offsets) is full-text-anchored; one with no passages was assessed against the
    candidate abstract. Derived from existing data — no schema change."""
    from ..state import StateError

    rated = anchored = 0
    for rid in store.list_support_ratings():
        try:
            r = store.load_support_rating(rid)
        except StateError:
            continue
        rated += 1
        human = r.human_rating.source_passages if r.human_rating else []
        ai = r.ai_rating.supporting_passages if r.ai_rating else []
        if human or ai:
            anchored += 1
    return {"rated": rated, "anchored": anchored, "abstract_only": rated - anchored}


def _basis_line(store) -> str:
    """One honest sentence on the evidence basis — empty when nothing is rated yet."""
    s = _basis_stats(store)
    if s["rated"] == 0:
        return ""
    was_were = "was" if s["anchored"] == 1 else "were"
    return (
        f"**Evidence basis.** Of {s['rated']} rated claim–candidate pair(s), {s['anchored']} "
        f"{was_were} assessed against at least one located full-text passage (a verbatim quote "
        f"with attachment and character offsets) and {s['abstract_only']} against the candidate "
        "abstract retrieved from PubMed. Abstract-only support is provisional — confirm such "
        "claims against the full text before relying on the citation.")


def _discovery_paragraph(store, ai_model_id, ai_model_snapshot=None) -> str:
    """The PRISMA-style identification disclosure: was an LLM in the discovery loop,
    and if so, exactly what did it do (propose leads) and not do (decide / rate)?"""
    s = _discovery_stats(store)
    if s["candidates"] == 0 and s["ai_claims"] == 0:
        return ("All claims and candidate references were identified by the authors; no "
                "large-language-model literature discovery was used in this ledger.")
    if s["ai_claims"] == 0:
        return (
            f"Candidate references ({s['candidates']} across {s['searches']} structured "
            f"PubMed search(es)) were staged as leads for the {s['n_claims']} author-"
            "identified claim(s). No large-language-model claim proposal was used. A human "
            "reviewer screened every candidate; no automated screening decision was made.")
    model = s["model"] or ai_model_id or "(model unset — pin ai_provenance.model_id)"
    # Name the snapshot/version too when it is pinned — a model id alone is not a
    # reproducible disclosure. Stays honest: omitted (not faked) when unset.
    snap = _shown(ai_model_snapshot, unset_hint="pin ai_provenance.model_snapshot")
    model = f"{model}, snapshot {snap}"
    was_were = "was" if s["ai_claims"] == 1 else "were"
    return (
        f"Candidate claims were identified with the assistance of a large language model "
        f"({model}) via CiteVahti's topic-screening and claim-extraction: the model "
        f"proposed candidate claims and CiteVahti staged candidate references from PubMed "
        f"as leads. Of {s['n_claims']} claim(s) under review, {s['ai_claims']} {was_were} "
        f"model-proposed (the remainder author-identified), and {s['candidates']} candidate "
        f"reference(s) were staged across {s['searches']} structured search(es). The model "
        "recorded no support rating and made no eligibility or inclusion decision — every "
        "inclusion decision and every support rating was made by a human reviewer (see the "
        "rating statement above). This LLM-assisted discovery aids identification only and "
        "is not automated screening; report it under the identification step of your PRISMA "
        "flow and disclose the model and date of use.")


def _prisma_flow(store) -> dict:
    """A PRISMA-style flow of evidence derived from the ledger: identification (records
    returned by the searches) → screening (records staged as candidate evidence) →
    assessed (claim–evidence pairs human-rated) → included (claims with accepted
    supporting evidence). Claim-level — each claim is a separate question — aggregated
    across the manuscript. No schema change; counts come from the existing ledger."""
    from ..state import StateError
    from .claim_report import ClaimReportService

    identified = 0
    batches = store.list_intake()
    for b in batches:
        try:
            rec = store.load_intake(b)
        except StateError:
            continue
        identified += rec.result_count if rec.result_count is not None else len(rec.hits)

    claims = store.list_claims()
    staged = 0
    for cid in claims:
        try:
            staged += len(store.load_candidates(cid).candidates)
        except StateError:
            pass

    rep = ClaimReportService(store).report()
    included = sum(1 for r in rep.rows if r.state == "accepted")
    return {"searches": len(batches), "identified": identified, "staged": staged,
            "assessed": len(store.list_support_ratings()), "included": included,
            "claims": len(claims)}


def _prisma_table(store) -> str:
    """A Markdown counts table for the PRISMA flow diagram — empty when the ledger is bare."""
    f = _prisma_flow(store)
    if not (f["claims"] or f["identified"]):
        return ""
    rows = [
        (f"Records identified — returned across {f['searches']} database search(es)", f["identified"]),
        (f"Records staged as candidate evidence for {f['claims']} claim(s)", f["staged"]),
        ("Claim–evidence pairs assessed (human-rated)", f["assessed"]),
        ("Supporting citations included (claims with accepted evidence)", f["included"]),
    ]
    body = "\n".join(f"| {label} | {n} |" for label, n in rows)
    return (
        "\n## Flow of evidence (PRISMA-style, derived from this ledger)\n\n"
        "Counts for the PRISMA flow diagram's *identification → screening → included* boxes. "
        "CiteVahti works at the **claim** level (each claim is a separate question), so these "
        "aggregate across the manuscript's claims and are **not** de-duplicated across "
        "searches — adapt them to your review's unit before reporting.\n\n"
        "| Stage | n |\n| --- | --: |\n" + body + "\n")


def build_methods_markdown(store) -> str:
    """Return the filled methods paragraph (Markdown) for this ledger."""
    from ..export import AgreementReportService

    cfg = store.load_config()
    prov = cfg.ai_provenance
    rep = AgreementReportService(store).report(
        metrics=["raw_agreement", "cohen_kappa", "adjudication_rate"])
    c = rep.overall
    raw = f"{c.agreements / c.comparable_pairs:.2f}" if c.comparable_pairs else "n/a (no comparable pairs yet)"

    para = _TEMPLATE.format(
        version=f"v{__version__}",
        provider=prov.provider or "(unset)",
        model_id=_shown(prov.model_id, unset_hint="pin ai_provenance.model_id"),
        snapshot=_shown(prov.model_snapshot, unset_hint="pin ai_provenance.model_snapshot"),
        prompt_version=_shown(prov.prompt_template_version, unset_hint="set ai_provenance.prompt_template_version"),
        blinding_mode=cfg.rating.order,
        n_pairs=c.comparable_pairs, n_agree=c.agreements, n_disagree=c.disagreements,
        n_abstain=c.ai_abstained, raw_agreement=raw, kappa=_kappa_str(rep))

    notes = []
    if not prov.is_model_pinned():
        notes.append("- The model provenance is not fully pinned — fill `ai_provenance` "
                     "in `.citevahti/config.json` before submission.")
    if not c.comparable_pairs:
        notes.append("- No comparable human–AI pairs yet — agreement and κ populate as "
                     "you record dual ratings.")
    note_block = ("\n\n**Before you submit:**\n" + "\n".join(notes)) if notes else ""

    basis = _basis_line(store)
    basis_block = (f"\n\n{basis}\n" if basis else "")
    discovery = _discovery_paragraph(store, prov.model_id, prov.model_snapshot)

    return (
        "# Methods statement (auto-filled)\n\n"
        "Paste into your manuscript's methods section and adapt. Numbers are this "
        "ledger's actual values; see `docs/REPORTING.md` for what each one means and "
        "the precise blinding wording.\n\n"
        f"> {para}\n{note_block}{basis_block}\n\n"
        "## How the literature was found (for PRISMA / systematic reviews)\n\n"
        "Paste under the *identification* step. This documents the role of any LLM in "
        "discovery — distinct from the human-only screening and rating above.\n\n"
        f"> {discovery}\n"
        + _prisma_table(store)
    )
