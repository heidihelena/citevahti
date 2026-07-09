#!/usr/bin/env python3
"""CiteVahti local-LLM prescreen benchmark.

Runs local Ollama models (default qwen3:14b, hermes3:8b) as prescreening AI
raters against an anchor label authored independently in the seed. Claude
ratings are carried in the seed as a third prescreener. Emits (to CWD):
  - results<tag>.json            full rating matrix + agreement stats
  - validation_records<tag>.jsonl CiteVahti ValidationRecord-shaped corpus
  - ratings_cache<tag>.json       so re-runs only re-query changed pairs
Usage: python3 bench.py <seed.json> [tag]
Stdlib only. Uses Ollama native /api/chat (think:false disables qwen3 CoT).
"""
import json, time, hashlib, unicodedata, urllib.request, urllib.error, sys, os
from pathlib import Path

OUT = Path.cwd()   # outputs are written to the current working directory
SEED_FILE = sys.argv[1] if len(sys.argv) > 1 else "seed.json"
TAG = sys.argv[2] if len(sys.argv) > 2 else ""   # output suffix, e.g. "_risk"
# Local models to test can be overridden: LOCAL_MODELS="qwen3:14b,hermes3:8b"
LOCAL_MODELS = [m.strip() for m in os.environ.get(
    "LOCAL_MODELS", "qwen3:14b,hermes3:8b").split(",") if m.strip()]
# Which local models are "thinking" models needing think:false (comma list)
THINKING = {m.strip() for m in os.environ.get("THINKING_MODELS", "qwen3:14b").split(",")}
SEED = json.loads(Path(SEED_FILE).read_text())
VOCAB = SEED["vocabulary"]  # supports, contrasts, unclear, not_relevant
OLLAMA = "http://localhost:11434/api/chat"

SYS = (
    "You are a citation prescreening agent. You are given a CLAIM and a SNIPPET "
    "from a cited source. Decide how the snippet relates to the claim. "
    "Respond ONLY with a JSON object: "
    '{"match_status": one of ["supports","contrasts","unclear","not_relevant"], '
    '"rationale": "one short sentence"}. '
    "Use 'supports' if the snippet backs the claim, 'contrasts' if it contradicts it, "
    "'unclear' if the snippet is on-topic but does not resolve the claim, and "
    "'not_relevant' if the snippet is about a different topic."
)

def claim_hash(text: str) -> str:
    n = unicodedata.normalize("NFC", text).lower()
    n = " ".join(n.split()).strip()
    return hashlib.sha256(n.encode("utf-8")).hexdigest()

def call_model(model: str, claim: str, snippet: str, think: bool):
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 220},
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content": f"CLAIM: {claim}\n\nSNIPPET: {snippet}"},
        ],
    }
    if not think:
        body["think"] = False
    data = json.dumps(body).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.loads(r.read())
    except Exception as e:  # noqa
        return {"status": "error", "raw": str(e), "secs": round(time.time() - t0, 1)}
    dt = round(time.time() - t0, 1)
    content = (out.get("message") or {}).get("content", "") or ""
    status, rationale = parse(content)
    return {"status": status, "rationale": rationale, "raw": content[:400], "secs": dt}

def parse(content: str):
    content = content.strip()
    try:
        obj = json.loads(content)
        ms = str(obj.get("match_status", "")).strip().lower()
        rat = str(obj.get("rationale", "")).strip()
    except Exception:
        low = content.lower()
        ms = next((v for v in VOCAB if v in low), "")
        rat = ""
    # normalize common variants
    aliases = {"support": "supports", "supported": "supports", "contradicts": "contrasts",
               "contrast": "contrasts", "contradict": "contrasts", "irrelevant": "not_relevant",
               "not relevant": "not_relevant", "notrelevant": "not_relevant", "unknown": "unclear"}
    ms = aliases.get(ms, ms)
    if ms not in VOCAB:
        return "unparseable", rat
    return ms, rat

def cohens_kappa(a, b):
    cats = VOCAB
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = 0.0
    for c in cats:
        pa = sum(1 for x in a if x == c) / n
        pb = sum(1 for x in b if x == c) / n
        pe += pa * pb
    if pe == 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 3)

def main():
    pairs = SEED["pairs"]
    theme = SEED["theme"]
    # rating cache: only query (pair, model) that are new or whose text changed
    cache_path = OUT / f"ratings_cache{TAG}.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    rows = []
    timings = {m: [] for m in LOCAL_MODELS}
    for p in pairs:
        row = {"id": p["id"], "claim": p["claim"], "snippet": p["snippet"],
               "source": p["source"], "ref": p["ref_status"],
               "ratings": {}, "rationales": {}}
        row["ratings"]["claude-fable-5"] = p["claude_status"]
        row["rationales"]["claude-fable-5"] = p["claude_rationale"]
        for model in LOCAL_MODELS:
            key = f"{p['id']}|{model}"
            c = cache.get(key)
            if c and c.get("claim") == p["claim"] and c.get("snippet") == p["snippet"]:
                res, tag = c, "cached"
            else:
                # thinking models (e.g. qwen3) need think=False; others omit it.
                res = call_model(model, p["claim"], p["snippet"], think=(model not in THINKING))
                res["claim"], res["snippet"] = p["claim"], p["snippet"]
                cache[key] = res
                tag = "live"
            row["ratings"][model] = res["status"]
            row["rationales"][model] = res.get("rationale", "")
            timings[model].append(res["secs"])
            print(f"  {p['id']} {model:14s} -> {res['status']:12s} ({res['secs']}s {tag})", flush=True)
        rows.append(row)
    cache_path.write_text(json.dumps(cache, indent=2))

    models = ["claude-fable-5"] + LOCAL_MODELS
    ref = [r["ref"] for r in rows]
    stats = {"vs_anchor": {}, "pairwise": {}, "timing_secs": {}}
    for m in models:
        col = [r["ratings"][m] for r in rows]
        valid = [(x, y) for x, y in zip(col, ref) if x in VOCAB]
        acc = round(sum(1 for x, y in valid if x == y) / len(rows), 3)
        parseable = sum(1 for x in col if x in VOCAB)
        stats["vs_anchor"][m] = {
            "accuracy_vs_anchor": acc,
            "cohens_kappa": cohens_kappa([x for x, _ in valid], [y for _, y in valid]),
            "parseable": f"{parseable}/{len(rows)}",
        }
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            a = [r["ratings"][models[i]] for r in rows]
            b = [r["ratings"][models[j]] for r in rows]
            va = [(x, y) for x, y in zip(a, b) if x in VOCAB and y in VOCAB]
            k = cohens_kappa([x for x, _ in va], [y for _, y in va])
            agree = round(sum(1 for x, y in va if x == y) / len(va), 3) if va else None
            stats["pairwise"][f"{models[i]} vs {models[j]}"] = {"agreement": agree, "cohens_kappa": k}
    for m in LOCAL_MODELS:
        ts = timings[m]
        stats["timing_secs"][m] = {"mean": round(sum(ts) / len(ts), 1),
                                   "min": min(ts), "max": max(ts)}

    results = {"theme": theme, "vocabulary": VOCAB, "models": models,
               "n_pairs": len(rows), "rows": rows, "stats": stats}
    (OUT / f"results{TAG}.json").write_text(json.dumps(results, indent=2))

    # CiteVahti ValidationRecord-shaped corpus (one line per pair x model)
    recs = []
    for r in rows:
        ch = claim_hash(r["claim"])
        for m in models:
            ai = r["ratings"][m]
            anchor = r["ref"]
            recs.append({
                "schema_version": "1.0",
                "record_id": "vr-" + hashlib.sha256((r["id"] + m).encode()).hexdigest()[:12],
                "created_at": "1970-01-01T00:00:00Z",
                "claim_type": theme.replace("-", "_"),
                "claim_text_hash": ch,
                "claim_text": r["claim"],
                "domain": f"{theme}::{m}",
                "pmid": None, "doi": None, "study_type": None,
                "ai_support_rating": ai if ai in VOCAB else None,
                "ai_confidence": None,
                "human_support_rating": anchor,
                "final_support_status": anchor,
                "final_decision": "accept" if ai == anchor else "review",
                "agreement_status": "concordant" if ai == anchor else "discordant",
            })
    with (OUT / f"validation_records{TAG}.jsonl").open("w") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")

    print("\n=== STATS ===")
    print(json.dumps(stats, indent=2))
    print(f"\nWrote results{TAG}.json ({len(rows)} pairs), "
          f"validation_records{TAG}.jsonl ({len(recs)} records)")

if __name__ == "__main__":
    main()
