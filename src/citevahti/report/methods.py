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

    return (
        "# Methods statement (auto-filled)\n\n"
        "Paste into your manuscript's methods section and adapt. Numbers are this "
        "ledger's actual values; see `docs/REPORTING.md` for what each one means and "
        "the precise blinding wording.\n\n"
        f"> {para}\n{note_block}\n"
    )
