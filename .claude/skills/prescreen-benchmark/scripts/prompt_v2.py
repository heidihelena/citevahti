#!/usr/bin/env python3
"""Re-run local models with an improved decision-workflow prompt (v2) that
scaffolds the 'unclear' verdict. Compares v2 to the stored v1 results.
Usage: python3 prompt_v2.py <seed.json> <results_v1.json>
"""
import json, time, sys, os, urllib.request
from pathlib import Path
SEED = json.loads(Path(sys.argv[1]).read_text())
V1 = json.loads(Path(sys.argv[2]).read_text())
VOCAB = SEED["vocabulary"]
OLLAMA = "http://localhost:11434/api/chat"

SYS_V2 = (
    "You are a citation prescreening agent. Given a CLAIM and a SNIPPET from a cited source, "
    "decide the relationship. Output ONLY JSON: {\"match_status\": one of "
    "[\"supports\",\"contrasts\",\"unclear\",\"not_relevant\"], \"rationale\": \"one sentence\"}.\n"
    "Decision rules, in order:\n"
    "1. not_relevant - the snippet is about a DIFFERENT topic than the claim.\n"
    "2. supports - the snippet AFFIRMS the claim is true.\n"
    "3. contrasts - the snippet STATES THE OPPOSITE of the claim (actively contradicts it).\n"
    "4. unclear - the snippet is ON-TOPIC but does NOT settle whether the claim is true. "
    "CRITICAL: if the snippet says the evidence is 'not established', 'inconclusive', 'uncertain', "
    "'mixed', 'limited', 'debated', 'under investigation', or 'an open question', answer 'unclear' "
    "- NOT 'contrasts'. 'The evidence does not establish X' means UNCLEAR, not that X is false. "
    "Also answer 'unclear' if the snippet only addresses a related but different point and leaves "
    "the specific claim unresolved.\n"
    "Do not answer 'supports' unless the snippet affirms the claim; do not answer 'contrasts' "
    "unless the snippet asserts the opposite."
)

def call(model, claim, snippet, think):
    body = {"model": model, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 220},
            "messages": [{"role": "system", "content": SYS_V2},
                         {"role": "user", "content": f"CLAIM: {claim}\n\nSNIPPET: {snippet}"}]}
    if not think:
        body["think"] = False
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read())
    content = (out.get("message") or {}).get("content", "") or ""
    try:
        ms = str(json.loads(content).get("match_status", "")).strip().lower()
    except Exception:
        ms = next((v for v in VOCAB if v in content.lower()), "unparseable")
    aliases = {"contradicts": "contrasts", "not relevant": "not_relevant", "irrelevant": "not_relevant"}
    ms = aliases.get(ms, ms)
    return ms if ms in VOCAB else "unparseable"

v1rows = {r["id"]: r for r in V1["rows"]}
models = [m.strip() for m in os.environ.get("LOCAL_MODELS", "qwen3:14b,hermes3:8b").split(",") if m.strip()]
THINKING = {m.strip() for m in os.environ.get("THINKING_MODELS", "qwen3:14b").split(",")}
res = {m: {"v2": [], "ref": [], "unclear_hit_v1": 0, "unclear_hit_v2": 0, "flips": []} for m in models}
n_unclear = 0
for p in SEED["pairs"]:
    ref = p["ref_status"]
    if ref == "unclear":
        n_unclear += 1
    for m in models:
        v2 = call(m, p["claim"], p["snippet"], think=(m not in THINKING))
        v1 = v1rows[p["id"]]["ratings"][m]
        res[m]["v2"].append(v2); res[m]["ref"].append(ref)
        if ref == "unclear":
            if v1 == "unclear": res[m]["unclear_hit_v1"] += 1
            if v2 == "unclear": res[m]["unclear_hit_v2"] += 1
        if v1 != v2:
            res[m]["flips"].append(f"{p['id']} {v1}->{v2} (anchor {ref})")
    print(".", end="", flush=True)
print()

def acc(v2, ref): return sum(1 for a, b in zip(v2, ref) if a == b) / len(ref)
print(f"\nTheme: {SEED['theme']}  ({len(SEED['pairs'])} pairs, {n_unclear} unclear)\n")
print(f"{'model':14s} {'v1 acc':>7s} {'v2 acc':>7s}   {'unclear v1':>10s} {'unclear v2':>10s}")
for m in models:
    v1acc = V1["stats"]["vs_anchor"][m]["accuracy_vs_anchor"]
    v2acc = acc(res[m]["v2"], res[m]["ref"])
    print(f"{m:14s} {v1acc:>6.0%} {v2acc:>7.0%}   {res[m]['unclear_hit_v1']:>7d}/{n_unclear} {res[m]['unclear_hit_v2']:>7d}/{n_unclear}")
print()
for m in models:
    print(f"{m} flips (v1->v2): " + ("; ".join(res[m]["flips"]) or "none"))
