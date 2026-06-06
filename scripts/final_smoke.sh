#!/usr/bin/env bash
# Final smoke test for CiteVahti — SAFE ONLY.
#
# Runs: the offline test suite, the startup probe, and an audit-chain check in a
# throwaway temp project. It performs NO Zotero writes and NO live PubMed call
# (PubMed is only exercised if you opt in explicitly; see the note below).
#
# Usage:
#   bash scripts/final_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

run() { echo; echo "=== $* ==="; "$@"; }

# 1) Full offline test suite (fake seams; no network).
run python3 -m pytest -q

# 2) Startup probe (read-only; reports availability + versions).
run python3 -m citevahti.cli probe || echo "(probe reported a degraded backend; that is fine)"

# 3) Audit-chain check in a disposable temp project (no user files touched).
SMOKE="$(mktemp -d)"
trap 'rm -rf "$SMOKE"' EXIT
run python3 -m citevahti.cli --root "$SMOKE" init
run python3 -m citevahti.cli --root "$SMOKE" verify-audit

echo
echo "final_smoke OK — no live writes, no live PubMed calls."
echo "To exercise a live PubMed query you must opt in explicitly with NCBI_EMAIL set,"
echo "e.g.: NCBI_EMAIL=you@example.org citevahti --root \"\$SMOKE\" literature-search --query 'cancer[Title]' --max-results 1"
