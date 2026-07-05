"""The Claude plugin manifest and the skills it lists must stay consistent, and the
skills must obey the house trust-language rule (check/assess, never verify/prove in
prose). Offline: reads repo files only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PLUGIN = _REPO / ".claude-plugin" / "plugin.json"
_SKILLS_DIR = _REPO / "skills"


def _listed_skills() -> list[str]:
    return json.loads(_PLUGIN.read_text(encoding="utf-8"))["skills"]


def test_every_listed_skill_exists_with_a_skill_md():
    missing = [s for s in _listed_skills() if not (_REPO / s / "SKILL.md").is_file()]
    assert not missing, f"plugin.json lists skills with no SKILL.md: {missing}"


def test_every_skill_on_disk_is_listed_in_the_manifest():
    on_disk = {f"skills/{d.name}" for d in _SKILLS_DIR.iterdir()
               if d.is_dir() and (d / "SKILL.md").is_file()}
    unlisted = sorted(on_disk - set(_listed_skills()))
    assert not unlisted, f"skills present but not in plugin.json: {unlisted}"


def test_skill_frontmatter_name_matches_its_directory():
    for s in _listed_skills():
        text = (_REPO / s / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"^name:\s*(.+)$", text, re.M)
        assert m, f"{s}/SKILL.md has no frontmatter name"
        assert m.group(1).strip() == Path(s).name, \
            f"{s}: frontmatter name {m.group(1).strip()!r} != dir {Path(s).name!r}"


# Skills this change introduced; the house trust-language rule (say check/assess, never
# verify/prove in prose) is enforced on them here. The two older skills predate this guard
# and carry legacy trust-language + a user-quoted "Verify" + the VS Code command label
# "CiteVahti: Verify claims"; cleaning those up is tracked separately, not conflated here.
_GUARDED_SKILLS = ("skills/citevahti-report", "skills/citevahti-screen", "skills/citevahti-review")


def test_new_skills_obey_house_trust_language():
    """PROSE in the newly-added skills must not promise verification/proof. Exempt: the
    command identifiers claim-verify / verify-audit (function-name exception), and any
    line that forbids/negates the word (a FORBIDDEN section says 'NEVER … verified')."""
    banned = re.compile(r"(verif(?:y|ied|ication)|proven?|prove[sd]?|guarantee[sd]?)", re.I)
    negated = re.compile(r"\b(never|not|n't|no|forbidden|don't|without|avoid|instead of)\b",
                         re.I)
    offenders: list[str] = []
    for s in _GUARDED_SKILLS:
        for i, line in enumerate((_REPO / s / "SKILL.md").read_text(encoding="utf-8").splitlines(), 1):
            if negated.search(line):
                continue
            for hit in banned.finditer(line):
                before = line[hit.start() - 1] if hit.start() else " "
                after = line[hit.end()] if hit.end() < len(line) else " "
                if before == "-" or after == "-":
                    continue                  # part of a hyphenated CLI token (claim-verify)
                offenders.append(f"{s}:{i}: …{line.strip()[:80]}…")
    assert not offenders, "trust-language violations (say check/assess):\n" + "\n".join(offenders)
