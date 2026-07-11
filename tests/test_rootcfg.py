"""One shared root resolver (audit §A.1): the CLI, the MCP server, and the panel all
answer "what am I working on" the same way. Precedence: explicit --root → $CITEVAHTI_ROOT
→ cwd-with-ledger → last-used root (with ledger) → home. Bare cwd is never the fallback."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from citevahti import rootcfg


def _ledger(dirpath: Path) -> Path:
    (dirpath / ".citevahti").mkdir(parents=True, exist_ok=True)
    return dirpath


def _isolate(monkeypatch, tmp_path):
    # isolate recents (XDG state file) and home so the test never reads the real machine
    home = _ledger(tmp_path / "home").parent / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CITEVAHTI_ROOT", raising=False)
    return home


def test_explicit_root_wins(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("CITEVAHTI_ROOT", str(tmp_path / "env"))
    assert rootcfg.resolve_root("/some/explicit") == "/some/explicit"
    assert rootcfg.resolve_root(".") != "/some/explicit"   # "." means "no explicit"


def test_env_beats_cwd_and_recents(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("CITEVAHTI_ROOT", str(tmp_path / "env"))
    monkeypatch.chdir(_ledger(tmp_path / "cwd"))
    assert rootcfg.resolve_root() == str(tmp_path / "env")


def test_cwd_with_ledger_beats_recents(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    rootcfg.remember_root(str(_ledger(tmp_path / "recent")))
    cwd = _ledger(tmp_path / "cwd")
    monkeypatch.chdir(cwd)
    assert rootcfg.resolve_root() == str(cwd.resolve())


def test_recents_used_when_cwd_has_no_ledger(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    recent = _ledger(tmp_path / "recent")
    rootcfg.remember_root(str(recent))
    bare = tmp_path / "bare"
    bare.mkdir(exist_ok=True)
    monkeypatch.chdir(bare)                 # no ledger here
    assert rootcfg.resolve_root() == str(recent.resolve())


def test_falls_back_to_home_never_bare_cwd(monkeypatch, tmp_path):
    home = _isolate(monkeypatch, tmp_path)
    bare = tmp_path / "bare"
    bare.mkdir(exist_ok=True)
    monkeypatch.chdir(bare)                 # cwd has no ledger → must NOT be returned
    got = rootcfg.resolve_root()
    assert got == str(home)
    assert got != str(bare)


def test_recents_ignored_if_ledger_gone(monkeypatch, tmp_path):
    home = _isolate(monkeypatch, tmp_path)
    recent = _ledger(tmp_path / "recent")
    rootcfg.remember_root(str(recent))
    (recent / ".citevahti").rmdir()         # the ledger disappeared
    bare = tmp_path / "bare"
    bare.mkdir(exist_ok=True)
    monkeypatch.chdir(bare)
    assert rootcfg.recall_root() is None
    assert rootcfg.resolve_root() == str(home)


# ---- leaked temp-dir roots (the cv-e2e-* incident) ---------------------------
# An e2e run that drove the real engine without isolating XDG_CONFIG_HOME wrote its
# throwaway ledger into the user's real state.json, and the installed app then opened
# the stale test ledger. Temp roots are refused unless the state file itself is
# temp-isolated (as pytest and well-behaved harnesses arrange).

def _pretend_real_config(monkeypatch):
    """Make ``_in_system_temp`` report the state file as NOT temp — as if it were the
    user's real ``~/.config`` — while every other path keeps its true classification.
    (tmp_path itself lives in the system temp tree, so this is the only way to exercise
    the unisolated case from a test.)"""
    state = rootcfg._global_state_path().expanduser().resolve()
    true_impl = rootcfg._in_system_temp
    monkeypatch.setattr(
        rootcfg, "_in_system_temp",
        lambda p: False if p.expanduser().resolve() == state else true_impl(p))


def test_in_system_temp_classification():
    assert rootcfg._in_system_temp(Path(tempfile.gettempdir()) / "cv-e2e-abc123")
    assert rootcfg._in_system_temp(Path("/var/folders/ab/cdef/T/cv-e2e-abc123"))
    assert rootcfg._in_system_temp(Path("/private/var/folders/ab/cdef/T/cv-e2e-x"))
    assert not rootcfg._in_system_temp(Path.home() / "Documents" / "CiteVahti")


def test_leaked_temp_root_not_remembered(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    good = _ledger(tmp_path / "good")
    rootcfg.remember_root(str(good))
    assert rootcfg.recall_root() == str(good.resolve())   # temp-isolated state: fine
    leaked = _ledger(tmp_path / "cv-e2e-leak")
    _pretend_real_config(monkeypatch)
    rootcfg.remember_root(str(leaked))      # refused — would leak into the real config
    data = json.loads(rootcfg._global_state_path().read_text(encoding="utf-8"))
    assert data["last_root"] == str(good.resolve())


def test_leaked_temp_root_not_recalled(monkeypatch, tmp_path):
    home = _isolate(monkeypatch, tmp_path)
    leaked = _ledger(tmp_path / "cv-e2e-leak")
    rootcfg.remember_root(str(leaked))      # an old engine already wrote the leak
    _pretend_real_config(monkeypatch)
    bare = tmp_path / "bare"
    bare.mkdir(exist_ok=True)
    monkeypatch.chdir(bare)
    assert rootcfg.recall_root() is None    # falls through instead of opening the leak
    assert rootcfg.resolve_root() == str(home)


# ---- recent manuscripts (working-file-selection idea 3) ----------------------
def test_recent_manuscripts_dedupe_order_and_cap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    a = _ledger(tmp_path / "proj-a")
    b = _ledger(tmp_path / "proj-b")
    rootcfg.remember_recent_manuscript(str(a), "paper-one.md")
    rootcfg.remember_recent_manuscript(str(b), "paper-two.md")
    rootcfg.remember_recent_manuscript(str(a), "paper-one.md")   # reopen → moves to front, no dupe
    recents = rootcfg.recall_recent_manuscripts()
    assert [(r["root"], r["id"]) for r in recents] == [
        (str(a.resolve()), "paper-one.md"), (str(b.resolve()), "paper-two.md")]
    for i in range(20):   # cap at 8
        rootcfg.remember_recent_manuscript(str(a), f"m{i}.md")
    assert len(rootcfg.recall_recent_manuscripts()) == 8


def test_recent_manuscripts_drop_rootless_and_keep_state_keys(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    gone = _ledger(tmp_path / "gone")
    keep = _ledger(tmp_path / "keep")
    rootcfg.remember_recent_manuscript(str(gone), "lost.md")
    rootcfg.remember_recent_manuscript(str(keep), "kept.md")
    import shutil
    shutil.rmtree(gone / ".citevahti")   # project ledger deleted → entry silently drops
    assert [r["id"] for r in rootcfg.recall_recent_manuscripts()] == ["kept.md"]
    # remember_root must PRESERVE the recents (state.json is shared, not clobbered)
    rootcfg.remember_root(str(keep))
    assert [r["id"] for r in rootcfg.recall_recent_manuscripts()] == ["kept.md"]
    assert rootcfg.recall_root() == str(keep.resolve())


def test_recent_manuscripts_never_record_leaked_temp_roots(monkeypatch, tmp_path):
    # real config (non-temp XDG) + a temp-tree project = a leaked e2e ledger; skip it
    monkeypatch.setenv("XDG_CONFIG_HOME", str(Path.home() / ".config-test-cv"))
    try:
        tmp_proj = _ledger(Path(tempfile.mkdtemp()) / "e2e")
        rootcfg.remember_recent_manuscript(str(tmp_proj), "temp.md")
        assert all(r["id"] != "temp.md" for r in rootcfg.recall_recent_manuscripts())
    finally:
        import shutil
        shutil.rmtree(Path.home() / ".config-test-cv", ignore_errors=True)
