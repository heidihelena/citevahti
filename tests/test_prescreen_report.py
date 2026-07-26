"""prescreen-benchmark report.py: renders any rater set, never invents a verdict.

The report is a skill script (stdlib-only, run via `python3`), so it is exercised as a
subprocess against synthetic results.json fixtures rather than imported.
"""

import json
import subprocess
import sys
from pathlib import Path

REPORT = (Path(__file__).resolve().parents[1]
          / ".claude/skills/prescreen-benchmark/scripts/report.py")

VOCAB = ["supports", "contrasts", "unclear", "not_relevant"]


def results(models, ratings_per_row, timed, theme="a-new-theme"):
    """Minimal results.json in bench.py's shape. ratings_per_row: list of dicts."""
    rows = [{"id": f"p{i + 1}", "claim": f"claim {i + 1}", "snippet": "s",
             "source": "Source et al.", "ref": ref, "ratings": dict(rat), "rationales": {}}
            for i, (ref, rat) in enumerate(ratings_per_row)]
    stats = {"vs_anchor": {}, "pairwise": {}, "timing_secs": {}}
    for m in models:
        col = [r["ratings"][m] for r in rows]
        hit = sum(1 for r, v in zip(rows, col) if v == r["ref"])
        parseable = sum(1 for v in col if v in VOCAB)
        stats["vs_anchor"][m] = {"accuracy_vs_anchor": round(hit / len(rows), 3),
                                 "cohens_kappa": 0.8 if parseable else None,
                                 "parseable": f"{parseable}/{len(rows)}"}
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            both = [(r["ratings"][a], r["ratings"][b]) for r in rows
                    if r["ratings"][a] in VOCAB and r["ratings"][b] in VOCAB]
            agree = round(sum(1 for x, y in both if x == y) / len(both), 3) if both else None
            stats["pairwise"][f"{a} vs {b}"] = {"agreement": agree,
                                                "cohens_kappa": 0.8 if both else None}
    for m in timed:
        stats["timing_secs"][m] = {"mean": 3.4, "min": 2.0, "max": 9.0}
    return {"theme": theme, "vocabulary": VOCAB, "models": models,
            "n_pairs": len(rows), "rows": rows, "stats": stats}


def render(tmp_path, payload):
    src = tmp_path / "results.json"
    src.write_text(json.dumps(payload))
    out = tmp_path / "report.html"
    proc = subprocess.run([sys.executable, str(REPORT), str(src), str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out.read_text()


def test_renders_the_original_two_locals_plus_peer_shape(tmp_path):
    models = ["claude-fable-5", "qwen3:14b", "hermes3:8b"]
    html = render(tmp_path, results(models, [
        ("supports", {"claude-fable-5": "supports", "qwen3:14b": "supports",
                      "hermes3:8b": "supports"}),
        ("unclear", {"claude-fable-5": "unclear", "qwen3:14b": "contrasts",
                     "hermes3:8b": "supports"}),
    ], timed=["qwen3:14b", "hermes3:8b"]))
    assert "Claude Fable 5" in html
    assert "Two local models" in html
    # the peer has verdicts, so it is scored, not reported absent
    assert "no verdicts recorded" not in html
    assert "qwen3:14b said &ldquo;contrasts&rdquo;" in html


def test_renders_a_model_set_it_has_no_labels_for(tmp_path):
    """An unlabelled model gets its raw id and a derived role, not a KeyError."""
    models = ["qwen3:14b", "hermes3:8b", "gemma3:12b"]
    html = render(tmp_path, results(models, [
        ("supports", {m: "supports" for m in models}),
        ("unclear", {"qwen3:14b": "unclear", "hermes3:8b": "supports",
                     "gemma3:12b": "unclear"}),
    ], timed=models))
    assert "Three local models" in html
    assert "gemma3:12b" in html
    assert "local &middot; 12B" in html or "local · 12B" in html
    # no reference peer in this run — the caveat must not claim one
    assert "reference peer included" not in html


def test_a_null_rater_column_is_absent_not_zero_percent(tmp_path):
    """bench.py writes null when a seed omits the Claude rater (shared-language confound)."""
    models = ["claude-fable-5", "qwen3:14b", "gemma3:12b"]
    html = render(tmp_path, results(models, [
        ("supports", {"claude-fable-5": None, "qwen3:14b": "supports",
                      "gemma3:12b": "supports"}),
        ("unclear", {"claude-fable-5": None, "qwen3:14b": "contrasts",
                     "gemma3:12b": "unclear"}),
    ], timed=["qwen3:14b", "gemma3:12b"]))
    assert "no verdicts recorded" in html
    assert "carries no verdicts in this run" in html
    # an empty column is never reported as a score, nor as a divergence from the anchor
    assert '<div class="cbig">&mdash;</div>' in html
    assert '<div class="cbig">0%' not in html
    assert "Claude Fable 5 said" not in html
