"""One shared root resolver (audit §A.1): the CLI, the MCP server, and the panel all
answer "what am I working on" the same way. Precedence: explicit --root → $CITEVAHTI_ROOT
→ cwd-with-ledger → last-used root (with ledger) → home. Bare cwd is never the fallback."""

from __future__ import annotations

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
