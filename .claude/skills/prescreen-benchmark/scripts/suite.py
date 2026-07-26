#!/usr/bin/env python3
"""Publish a held-out prescreen suite, and pack/validate a leaderboard submission.

The board is open: any rater — a local model, a hosted API, an ensemble, a human
expert — screens the same published items and submits its verdicts. Scores are
computed by whoever holds the answer key, never taken from the submitter.

  suite.py export <seed.json> <suite_id> [outdir]
      -> suite_<suite_id>.json   PUBLIC: claims + snippets, no anchors
      -> key_<suite_id>.json     PRIVATE: the answer key. Never publish this.
  suite.py template <suite.json> [out.jsonl]
      -> verdicts.jsonl skeleton for a submitter to fill in
  suite.py pack <verdicts.jsonl> <suite.json> --rater <id> --rater-kind <kind> ...
      -> submission.json bound to the verdicts by content hash
      (owner shortcut: --from-results <results.json> --key <key.json> instead of
       a verdicts file, to submit a run this skill's bench.py already produced)
  suite.py validate <submission.json> <verdicts.jsonl> <suite.json>
      -> exit 0 if the submission is well-formed; the check CI runs, key-free

Held-out means the item ids, ordering, strata and anchor rationale never reach
the public file: in this skill's seeds the stratum *is* the anchor (A=supports,
B=contrasts, C=not_relevant, D=unclear) and ids are A01/B03..., so publishing
them verbatim would publish the key. Export re-ids and reorders deterministically.

Stdlib only. Paths are CWD-relative.
"""
import argparse, hashlib, json, sys, unicodedata
from pathlib import Path

SCHEMA = "citevahti.prescreen/1"
# Fields that carry the anchor, directly or by construction. None may appear in
# a public suite or in a submission — mirrors CorpusVahti's "never trust the
# client's de-id" guard: the leak check runs on our side, every time.
ANCHOR_FIELDS = {"ref_status", "anchor", "anchor_basis", "stratum", "claude_status",
                 "claude_rationale", "ref"}


def text_hash(text):
    """The frozen cross-tool normalization: NFC -> lower -> collapse ws -> trim -> SHA-256.

    Byte-identical to bench.py's claim_hash and to MatchVahti's claim_text_hash.
    Changing it forks the corpus — don't.
    """
    n = unicodedata.normalize("NFC", text).lower()
    n = " ".join(n.split()).strip()
    return hashlib.sha256(n.encode("utf-8")).hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def pair_set_hash(items):
    """Content address of the item set: anyone holding the public file can recompute it."""
    body = "\n".join(f'{i["item_id"]}\t{i["claim_text_hash"]}\t{i["snippet_hash"]}'
                     for i in sorted(items, key=lambda i: i["item_id"]))
    return sha256_bytes(body.encode("utf-8"))


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def all_keys(obj):
    """Every dict key anywhere in a JSON structure — used by the anchor-leak guard."""
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in all_keys(v)}
    return set()


# ---------------------------------------------------------------- export

def cmd_export(args):
    seed = json.loads(Path(args.seed).read_text())
    pairs = seed["pairs"]
    suite_id = args.suite_id
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Deterministic, seed-derived shuffle. Publishing A01..A14 then B01..B10 in
    # order would leak the key by position just as the ids leak it by name.
    def shuffle_key(p):
        return sha256_bytes(f"{suite_id}\x00{p['id']}".encode("utf-8"))

    ordered = sorted(pairs, key=shuffle_key)
    width = max(3, len(str(len(ordered))))
    items, key_rows = [], []
    for n, p in enumerate(ordered, start=1):
        item_id = f"i{n:0{width}d}"
        items.append({"item_id": item_id, "claim": p["claim"], "snippet": p["snippet"],
                      "source": p["source"],
                      "claim_text_hash": text_hash(p["claim"]),
                      "snippet_hash": text_hash(p["snippet"])})
        key_rows.append({"item_id": item_id, "seed_id": p["id"],
                         "anchor": p["ref_status"], "stratum": p.get("stratum"),
                         "anchor_basis": p.get("anchor_basis")})

    suite = {"schema": SCHEMA, "kind": "suite", "suite_id": suite_id,
             "theme": seed["theme"], "vocabulary": seed["vocabulary"],
             "n_items": len(items), "anchor_visibility": "held_out",
             # Say what the anchors are, so the board can't be read as more than it is.
             "anchor_provenance": seed.get("anchor_provenance"),
             "items": items}
    suite["pair_set_hash"] = pair_set_hash(items)

    leaked = sorted(ANCHOR_FIELDS & all_keys(suite))
    if leaked:                                  # belt and braces: never ship the key
        die(f"public suite would leak anchor fields: {', '.join(leaked)}")

    key = {"schema": SCHEMA, "kind": "key", "suite_id": suite_id,
           "pair_set_hash": suite["pair_set_hash"], "items": key_rows}

    sp = outdir / f"suite_{suite_id}.json"
    kp = outdir / f"key_{suite_id}.json"
    sp.write_text(json.dumps(suite, indent=2, ensure_ascii=False) + "\n")
    kp.write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {sp} ({len(items)} items, pair_set_hash {suite['pair_set_hash'][:16]}…)")
    print(f"Wrote {kp}  — PRIVATE, never publish or commit to a public repo")


# ---------------------------------------------------------------- template

def cmd_template(args):
    suite = json.loads(Path(args.suite).read_text())
    out = Path(args.out)
    out.write_text("".join(
        json.dumps({"item_id": i["item_id"], "verdict": None, "latency_ms": None}) + "\n"
        for i in suite["items"]))
    print(f"Wrote {out} — fill in each verdict with one of: "
          f"{', '.join(suite['vocabulary'])} (or leave null if the rater gave no usable answer)")


# ---------------------------------------------------------------- pack

def read_verdicts(path):
    rows = []
    for n, line in enumerate(Path(path).read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            die(f"{path}:{n}: not valid JSON ({e.msg})")
    return rows


def cmd_pack(args):
    suite = json.loads(Path(args.suite).read_text())
    if args.from_results:
        if not args.key:
            die("--from-results needs --key (the run uses seed ids; the key maps them)")
        results = json.loads(Path(args.from_results).read_text())
        key = json.loads(Path(args.key).read_text())
        if key["suite_id"] != suite["suite_id"]:
            die(f"key is for suite {key['suite_id']}, suite file is {suite['suite_id']}")
        by_seed = {k["seed_id"]: k["item_id"] for k in key["items"]}
        if args.rater not in results.get("models", []):
            die(f"{args.rater} is not a rater in {args.from_results}: "
                f"{', '.join(results.get('models', []))}")
        rows = []
        for r in results["rows"]:
            if r["id"] not in by_seed:
                die(f"results row {r['id']} is not in the key for this suite")
            rows.append({"item_id": by_seed[r["id"]],
                         "verdict": r["ratings"].get(args.rater), "latency_ms": None})
        verdicts_path = Path(args.out).with_name("verdicts.jsonl")
        verdicts_path.write_text("".join(
            json.dumps(v) + "\n" for v in sorted(rows, key=lambda v: v["item_id"])))
        print(f"Wrote {verdicts_path} ({len(rows)} verdicts from {args.from_results})")
    else:
        if not args.verdicts:
            die("give a verdicts.jsonl, or --from-results with --key")
        verdicts_path = Path(args.verdicts)

    raw = verdicts_path.read_bytes()
    submission = {
        "schema": SCHEMA, "kind": "submission",
        "suite_id": suite["suite_id"], "pair_set_hash": suite["pair_set_hash"],
        "rater": {"id": args.rater, "kind": args.rater_kind,
                  "params": json.loads(args.rater_params) if args.rater_params else {}},
        "prompt": {"id": args.prompt_id, "hash": text_hash(args.prompt_text)
                   if args.prompt_text else args.prompt_hash},
        "path": args.path, "harness_version": args.harness_version,
        "verdicts_file": verdicts_path.name, "verdicts_sha256": sha256_bytes(raw),
    }
    Path(args.out).write_text(json.dumps(submission, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {args.out} — submit it with {verdicts_path.name}")


# ---------------------------------------------------------------- validate

def cmd_validate(args):
    sub = json.loads(Path(args.submission).read_text())
    suite = json.loads(Path(args.suite).read_text())
    rows = read_verdicts(args.verdicts)
    problems = []

    def bad(m):
        problems.append(m)

    if sub.get("schema") != SCHEMA:
        bad(f"schema is {sub.get('schema')!r}, expected {SCHEMA!r}")
    if sub.get("kind") != "submission":
        bad(f"kind is {sub.get('kind')!r}, expected 'submission'")
    if sub.get("suite_id") != suite["suite_id"]:
        bad(f"suite_id {sub.get('suite_id')!r} != suite {suite['suite_id']!r}")
    if sub.get("pair_set_hash") != suite["pair_set_hash"]:
        bad("pair_set_hash does not match the suite — the item set was edited, "
            "so the run is not comparable")
    if suite["pair_set_hash"] != pair_set_hash(suite["items"]):
        bad("the suite file's own pair_set_hash does not match its items")
    # Re-derive each item's hashes from its text. Without this the content
    # address is only as good as the hash fields somebody typed into the file:
    # an edited claim with an untouched claim_text_hash would pass every check
    # above, and the submitter would have rated text nobody else saw.
    for i in suite["items"]:
        if text_hash(i["claim"]) != i["claim_text_hash"]:
            bad(f'{i["item_id"]}: claim text does not match its claim_text_hash')
        if text_hash(i["snippet"]) != i["snippet_hash"]:
            bad(f'{i["item_id"]}: snippet text does not match its snippet_hash')
    if suite.get("n_items") != len(suite["items"]):
        bad(f'suite says n_items={suite.get("n_items")} but carries {len(suite["items"])} items')

    raw = Path(args.verdicts).read_bytes()
    if sub.get("verdicts_sha256") != sha256_bytes(raw):
        bad("verdicts_sha256 does not match the verdicts file")

    for field, where in (("rater", "id"), ("rater", "kind"), ("prompt", "id"), ("prompt", "hash")):
        if not (sub.get(field) or {}).get(where):
            bad(f"missing {field}.{where} — a run without it can't be compared")

    # A submission carries verdicts, never the key. Same guard as export.
    leaked = sorted(ANCHOR_FIELDS & (all_keys(sub) | all_keys(rows)))
    if leaked:
        bad(f"submission carries anchor field(s): {', '.join(leaked)}")

    want = [i["item_id"] for i in suite["items"]]
    got = [r.get("item_id") for r in rows]
    missing, extra = set(want) - set(got), set(got) - set(want)
    if missing:
        bad(f"{len(missing)} item(s) have no verdict, e.g. {sorted(missing)[:3]} — "
            f"submit an explicit null instead of omitting the row")
    if extra:
        bad(f"{len(extra)} verdict(s) for unknown item(s), e.g. {sorted(extra)[:3]}")
    if len(got) != len(set(got)):
        dupes = sorted({i for i in got if got.count(i) > 1})
        bad(f"duplicate verdict rows: {dupes[:3]}")

    vocab = set(suite["vocabulary"])
    for r in rows:
        v = r.get("verdict")
        if v is not None and v not in vocab:
            bad(f'{r.get("item_id")}: verdict {v!r} is outside the frozen vocabulary '
                f'({", ".join(suite["vocabulary"])}); use null for no usable answer')

    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        raise SystemExit(1)
    answered = sum(1 for r in rows if r.get("verdict") is not None)
    print(f"ok: {sub['rater']['id']} on {suite['suite_id']} — {len(rows)} items, "
          f"{answered} answered, {len(rows) - answered} null")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="split a seed into a public suite + a private key")
    e.add_argument("seed"), e.add_argument("suite_id")
    e.add_argument("outdir", nargs="?", default=".")
    e.set_defaults(func=cmd_export)

    t = sub.add_parser("template", help="empty verdicts.jsonl for a submitter")
    t.add_argument("suite"), t.add_argument("out", nargs="?", default="verdicts.jsonl")
    t.set_defaults(func=cmd_template)

    p = sub.add_parser("pack", help="build submission.json bound to a verdicts file")
    p.add_argument("verdicts", nargs="?")
    p.add_argument("suite")
    p.add_argument("--out", default="submission.json")
    p.add_argument("--rater", required=True, help="e.g. qwen3:14b, gpt-5, human:expert-a")
    p.add_argument("--rater-kind", required=True,
                   choices=["local", "hosted_api", "human", "ensemble"])
    p.add_argument("--rater-params", help="JSON: quantization, temperature, hardware…")
    p.add_argument("--prompt-id", required=True, help="e.g. prescreen-v1, prescreen-v2")
    p.add_argument("--prompt-hash", help="hash of the exact prompt text")
    p.add_argument("--prompt-text", help="the prompt itself; hashed for you")
    p.add_argument("--path", default="skill", choices=["skill", "product"])
    p.add_argument("--harness-version", default="")
    p.add_argument("--from-results", help="a results.json from this skill's bench.py")
    p.add_argument("--key", help="key_<suite>.json, to map seed ids (owner only)")
    p.set_defaults(func=cmd_pack)

    v = sub.add_parser("validate", help="the key-free structural check CI runs")
    v.add_argument("submission"), v.add_argument("verdicts"), v.add_argument("suite")
    v.set_defaults(func=cmd_validate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
