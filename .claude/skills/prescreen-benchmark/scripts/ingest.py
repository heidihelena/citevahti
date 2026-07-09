#!/usr/bin/env python3
"""Ingest a benchmark corpus into a DEDICATED CiteVahti store.

Always use a separate --root so a real pilot ledger is never touched.
Human rating = the seed anchor. AI rating = one local model's prescreen (blind);
where they diverge, the anchor adjudicates. Requires the store to be initialised
first: `citevahti --root <ROOT> init`.

Usage: PYTHONPATH=<repo>/src python3 ingest.py <results.json> <ROOT> [panel_model]
"""
import json, os, sys
from pathlib import Path

RESULTS_FILE = sys.argv[1] if len(sys.argv) > 1 else "results.json"
ROOT = os.path.expanduser(sys.argv[2] if len(sys.argv) > 2
                          else "~/Documents/CiteVahti-benchmark")
PANEL_MODEL = sys.argv[3] if len(sys.argv) > 3 else "qwen3:14b"
RESULTS = json.loads(Path(RESULTS_FILE).read_text())
THEME = RESULTS.get("theme", "prescreen-benchmark")

from citevahti import tools
from citevahti.claims import ClaimService, ClaimSupportEngine, DecisionService
from citevahti.schemas.candidate import ClaimPaperCandidate, ClaimCandidates
from citevahti.schemas.common import Provenance

PROV = Provenance(tool="prescreen-benchmark", tool_version="1.0",
                  ran_at="1970-01-01T00:00:00Z", config_hash="benchseed",
                  sources=[{"source": "manual", "note": "anchored snippet seed"}])

# coarse prescreen vocab -> CiteVahti 7-value support vocab
MAP = {"supports": "directly_supports", "contrasts": "contradicts",
       "unclear": "unclear", "not_relevant": "does_not_support"}

def main():
    Path(ROOT).mkdir(parents=True, exist_ok=True)
    store = tools._open_store(ROOT)

    # pin the local model so AI ratings are allowed + carry honest provenance
    cfg = store.load_config()
    cfg.ai_provenance.provider = "ollama"
    cfg.ai_provenance.model_id = PANEL_MODEL
    cfg.ai_provenance.model_snapshot = f"ollama:{PANEL_MODEL}"
    cfg.ai_provenance.prompt_template_version = f"{THEME}-prescreen-1"
    store.save_config(cfg)

    claim_svc = ClaimService(store)
    engine = ClaimSupportEngine(store, config=store.load_config())
    dec_svc = DecisionService(store)

    n = 0
    for row in RESULTS["rows"]:
        anchor = MAP[row["ref"]]
        ai_val = MAP.get(row["ratings"][PANEL_MODEL])
        # 1. claim
        claim = claim_svc.add_claim(row["claim"], "other",
                                    manuscript_location=row["id"], extracted_by="human")
        cid = claim.claim_id
        # 2. candidate (the cited source), manual provenance
        cand = ClaimPaperCandidate(
            candidate_id=f"cand-{row['id']}", claim_id=cid,
            retrieval_source="manual", retrieval_query=row["claim"],
            why_found="lung-nodule benchmark seed", title=row["source"],
            abstract=row["snippet"])
        store.save_candidates(ClaimCandidates(claim_id=cid, candidates=[cand], provenance=PROV))
        # 3. blinded support rating: human (anchor) first, then AI (qwen prescreen)
        rating = engine.support_start(cid, cand.candidate_id)
        rid = rating.rating_id
        engine.support_commit_human(rid, anchor, rationale=f"Guideline-derived anchor ({row['source']}).",
                                    committed_by="guideline-anchor")
        if ai_val:
            engine.submit_ai_rating(rid, ai_val, confidence=0.7,
                                    reasoning=row["rationales"].get(PANEL_MODEL, ""),
                                    task_type="assess")
        engine.support_compare(rid)
        # discordant AI vs human anchor -> adjudicate to the anchor (only path to final)
        concord = (row["ratings"][PANEL_MODEL] == row["ref"])
        if not concord and ai_val is not None:
            engine.support_adjudicate(rid, anchor,
                                      "Anchor (guideline) decides; AI prescreen diverged.",
                                      decider="human")
        # 4. decision — must be consistent with the final support value
        SUPPORTING = ("directly_supports", "partially_supports", "indirectly_supports")
        if anchor in SUPPORTING:
            fd, why = "accept", "Cited source supports the claim (anchor-confirmed)."
        elif anchor == "unclear":
            fd, why = "needs_second_review", "Source does not resolve the claim."
        else:  # contradicts / does_not_support
            fd, why = "reject", "Cited source does not support / contradicts the claim."
        dec_svc.decide(cid, cand.candidate_id, fd, why,
                       rating_id=rid, decided_by="guideline-anchor")
        n += 1
        print(f"  {row['id']}: human={anchor} ai={ai_val} -> {fd} "
              f"({'concordant' if concord else 'DISCORDANT'})", flush=True)

    em = tools.evidence_map(root=ROOT)
    print(f"\nIngested {n} claims into {ROOT}")
    print(f"evidence_map: {em['counts']}  warnings={em.get('warnings')}")

if __name__ == "__main__":
    main()
