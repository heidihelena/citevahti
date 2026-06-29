# Panel frontend tests

Behaviour tests for the CiteVahti loopback panel (the served vanilla-JS app in
`src/citevahti/panel/web/`). **No build step** — the tests load the real shipped scripts.
Everything asserts what a user sees/does; nothing pokes internals.

## Layout

| File | Category | Runner |
|---|---|---|
| `units.test.mjs` | 1 · pure logic (recency labels, project names, audit vocabulary, references) | `node:test` |
| `components.test.mjs` | 2 · key interactions (intake, nav, hand-off, review-record modal, export cards) | `node:test` + jsdom |
| `errors.test.mjs` | 4 · error paths (empty input, export/setup/reveal failures, the wait-timeout help) | `node:test` + jsdom |
| `a11y.test.mjs` | 5 · accessibility (named dialogs, Escape, the keyboard audit button, labelled regions) | `node:test` + jsdom |
| `e2e/flow.spec.mjs` | 3 · full user flow in a real browser | Playwright |
| `e2e/a11y.spec.mjs` | 5 · interactive a11y (focus-trap, keyboard nav) | Playwright |
| `harness.mjs` | boots the real app into a jsdom window with a routable `fetch` mock | — |

The jsdom harness loads the production `index.html` skeleton + the concatenated panel
scripts so the app boots with its **real** event wiring; tests interact through the DOM
(click a button, read what appears). A small set of pure functions is exposed for unit tests.

## Run

```bash
cd frontend-tests
npm install                       # jsdom + @playwright/test (once)

npm test                          # unit + component + error + a11y  (fast, no browser)

npx playwright install chromium   # once, for e2e
npm run e2e                       # full flow + interactive a11y (starts the panel server
                                  # against a throwaway copy of .demo-ledger)
```

From pytest (skips cleanly when deps aren't installed):

```bash
pytest tests/test_frontend.py                 # node:test suite
CITEVAHTI_E2E=1 pytest tests/test_frontend.py  # + Playwright (needs the browser + .demo-ledger)
```

## Notes

- **Pinned, reproducible:** `package-lock.json` is committed; `node_modules/` and Playwright
  output are git-ignored.
- **e2e is opt-in** (`CITEVAHTI_E2E=1`) because it downloads a browser and starts the Python
  server. It needs a demo ledger at `.demo-ledger` (regenerate with `docs/demo/build_demo_ledger.py`).
- These run against the **shipped** files — no transpile, no mock of the app itself; only
  `fetch` (jsdom) or the loopback server (Playwright) is the boundary.
