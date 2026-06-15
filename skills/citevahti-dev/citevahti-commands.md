# CiteVahti — Full Command Reference

## Setup
```bash
citevahti init
citevahti onboard --ncbi-email EMAIL --no-zotero-key --skip-validate
citevahti connect-zotero
citevahti probe
```

## Claim loop
```bash
citevahti claim-add --text "..." --type effectiveness --location "§2"
citevahti claim-untestable <claim-id> --reason "monograph, not indexed"
citevahti literature-search --query "..." --question-id q1
citevahti claim-link-candidates --claim-id CID --intake-batch-id BID
citevahti candidate-list --claim-id CID
```

## Rating
```bash
citevahti claim-support-start --claim-id CID --candidate-id CANDID
citevahti claim-support-commit-human --rating-id RID --value directly_supports
# values: directly_supports | partially_supports | indirectly_supports | does_not_support | contradicts | unclear
citevahti claim-support-compare --rating-id RID
```

## Decision + write
```bash
citevahti claim-decide --claim-id CID --candidate-id CANDID \
  --decision accept --reason "RCT directly evaluates the claim" --rating-id RID
citevahti claim-commit --decision-id DID            # dry-run preview only
citevahti claim-commit --decision-id DID --commit   # preview → [y/N] → write
citevahti txn-undo --transaction-id TXN             # undo any time
```

## Non-interactive / CI
```bash
TOKEN=$(citevahti claim-commit --decision-id DID --json \
  | python -c "import sys,json;print(json.load(sys.stdin)['confirm_token'])")
citevahti claim-commit --decision-id DID --commit --confirm-token "$TOKEN"
```

## Reports
```bash
citevahti claim-report                              # 4-state summary
citevahti claim-report --format md --output integrity.md
citevahti agreement-report --format markdown        # methods-section text
citevahti verify-audit                              # hash-chain check
```

## Support-rating values (`--value`)
directly_supports | partially_supports | indirectly_supports | does_not_support | contradicts | unclear

`untestable` is a separate claim *status*, set via `citevahti claim-untestable <claim-id>` — not a support-rating value.

## Decision values (`--decision`)
accept | accepted_with_caution | needs_second_review | reject

Shown in the panel/report as the bracket codes: `[oo]` accept · `[o]` accepted_with_caution · `[r]` needs_second_review · `[d]` reject.

## MCP config (Claude Code)
```
claude mcp add citevahti -- citevahti start --root /path/to/project
```

## MCP config (Claude Desktop JSON)
```json
{"mcpServers":{"citevahti":{"command":"citevahti","args":["start","--root","/path/to/project"]}}}
```
