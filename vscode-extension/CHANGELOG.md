# Changelog — CiteVahti VS Code extension

## 0.17.0

- Version bump to track the **`citevahti` CLI 0.17.0** (manuscript unit tests, inline
  claim editing, the warehouse/Atlas contribution surface, and FullVahti tag write-back —
  all driven through the CLI the extension shells out to). No change to the extension's
  own commands; set `citevahti.cliPath` to a 0.17.0 binary to pick up the new capabilities.

## 0.16.0

- **`[oo]` claim state renamed Verified → Accepted** to match the engine — "accepted"
  means *has an accepted, supporting citation*, not a claim of clinical/scientific truth.
  Keyboard flow and short codes (`oo/o/r/d`) are unchanged.
- The extension now **reads the verdict vocabulary from `citevahti vocabulary`** at
  activation, so its decision keys can't silently drift from the engine
  (`schemas/decision.py`); it falls back to the built-in map if the CLI is older.
- Requires the **`citevahti` CLI 0.16.0+** — set `citevahti.cliPath` to your `citevahti`
  binary (e.g. `.venv/bin/citevahti`).

_Earlier 0.x releases tracked the CLI; see the repository [CHANGELOG](https://github.com/heidihelena/citevahti/blob/main/CHANGELOG.md)._
