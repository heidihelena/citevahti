"""The auto-updater must be safe by default: inert until configured, graceful on
failure, and never a silent self-apply. These run fully offline — no tufup, no
network — via injected fakes and the not-configured path."""

from __future__ import annotations

from pathlib import Path

from citevahti.autoupdate import check_for_update, apply_update, resolve_settings
from citevahti.autoupdate.client import (
    APPLIED, AVAILABLE, NOT_CONFIGURED, UNAVAILABLE, UP_TO_DATE,
)
from citevahti.autoupdate.maintainer import add_release, init_repository
from citevahti.autoupdate.settings import AutoUpdateSettings


def _configured(tmp_path: Path, version: str = "0.40.0") -> AutoUpdateSettings:
    root = tmp_path / "root.json"
    root.write_text("{}")
    return AutoUpdateSettings(
        app_name="CiteVahti", current_version=version,
        update_url="https://updates.example/citevahti", trusted_root=root,
        install_dir=tmp_path / "install", metadata_dir=tmp_path / "md",
        target_dir=tmp_path / "tg", frozen=True,
    )


class _FakeTarget:
    def __init__(self, version: str):
        self.version = version


class _FakeClient:
    def __init__(self, *, new=None, raises=None):
        self._new, self._raises, self.applied = new, raises, False

    def check_for_updates(self):
        if self._raises:
            raise self._raises
        return self._new

    def download_and_apply_update(self, **_kw):
        self.applied = True


# ---- inert by default ------------------------------------------------------
def test_default_settings_are_inert_under_pytest():
    # pytest is not a frozen app → the updater must report itself not-configured.
    s = resolve_settings()
    assert s.is_configured() is False
    assert "frozen" in s.why_inert()


def test_check_is_a_noop_when_not_configured():
    out = check_for_update()  # no settings → resolve → not configured
    assert out.status == NOT_CONFIGURED
    assert out.update_available is False


def test_apply_refuses_when_not_configured():
    assert apply_update().status == NOT_CONFIGURED


# ---- check: configured, via an injected fake client ------------------------
def test_check_reports_up_to_date(tmp_path):
    out = check_for_update(_configured(tmp_path), client_factory=lambda _s: _FakeClient(new=None))
    assert out.status == UP_TO_DATE


def test_check_reports_an_available_version(tmp_path):
    out = check_for_update(
        _configured(tmp_path),
        client_factory=lambda _s: _FakeClient(new=_FakeTarget("0.41.0")),
    )
    assert out.status == AVAILABLE
    assert out.version == "0.41.0"
    assert out.update_available is True


def test_check_degrades_to_unavailable_on_error(tmp_path):
    out = check_for_update(
        _configured(tmp_path),
        client_factory=lambda _s: _FakeClient(raises=RuntimeError("server down")),
    )
    assert out.status == UNAVAILABLE
    assert "server down" in out.detail


# ---- apply: only the post-consent path, still graceful ---------------------
def test_apply_runs_only_after_a_real_update_and_reports_applied(tmp_path):
    fake = _FakeClient(new=_FakeTarget("0.41.0"))
    out = apply_update(_configured(tmp_path), client_factory=lambda _s: fake)
    assert out.status == APPLIED
    assert fake.applied is True


def test_apply_does_nothing_when_already_up_to_date(tmp_path):
    fake = _FakeClient(new=None)
    out = apply_update(_configured(tmp_path), client_factory=lambda _s: fake)
    assert out.status == UP_TO_DATE
    assert fake.applied is False


# ---- maintainer wiring (injected repo, no tufup) ---------------------------
class _FakeRepo:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def initialize(self):
        self.calls.append("initialize")

    def add_bundle(self, **kw):
        self.calls.append(("add_bundle", kw))

    def publish_changes(self, **kw):
        self.calls.append(("publish_changes", kw))


def test_init_repository_initializes(tmp_path):
    repo = init_repository(tmp_path / "repo", tmp_path / "keys",
                           repo_factory=lambda **kw: _FakeRepo(**kw))
    assert "initialize" in repo.calls


def test_add_release_adds_bundle_and_publishes_with_offline_keys(tmp_path):
    keys = tmp_path / "keys"
    repo = add_release(tmp_path / "repo", keys, tmp_path / "bundle", "0.41.0",
                       repo_factory=lambda **kw: _FakeRepo(**kw))
    names = [c[0] if isinstance(c, tuple) else c for c in repo.calls]
    assert names == ["add_bundle", "publish_changes"]
    publish = next(c for c in repo.calls if c[0] == "publish_changes")
    assert publish[1]["private_key_dirs"] == [str(keys)]   # signs with the offline keys


# ---- launch hook never breaks a launch -------------------------------------
def test_desktop_announce_update_is_silent_and_safe(capsys):
    from citevahti.desktop import _announce_update

    _announce_update()  # not configured → prints nothing, raises nothing
    assert capsys.readouterr().out == ""


# ---- panel wiring: the prompted "Update now / Later" UX --------------------
def test_panel_app_update_status_endpoint_is_read_only_and_inert(tmp_path):
    # GET /api/app-update surfaces the frozen-app updater STATUS for the panel prompt.
    # Under pytest (not frozen) it must be inert — no network, status not_configured.
    from citevahti.panel.server import _GET_ROUTES, dispatch

    assert "/api/app-update" in _GET_ROUTES
    status, body = dispatch(str(tmp_path), "GET", "/api/app-update", None)
    assert status == 200
    assert body["status"] == NOT_CONFIGURED
    assert body["update_available"] is False


def test_panel_app_update_apply_is_a_mutating_post_and_inert(tmp_path):
    # The apply endpoint is registered as a POST (so it inherits the CSRF choke point in
    # do_POST, above dispatch — the missing-token rejection is frozen in
    # test_panel_route_perimeter). Post-consent only, and inert without keys+server.
    from citevahti.panel.server import _POST_ROUTES, dispatch

    assert "/api/app-update/apply" in _POST_ROUTES
    status, body = dispatch(str(tmp_path), "POST", "/api/app-update/apply", {})
    assert status == 200
    assert body["status"] == NOT_CONFIGURED   # nothing is ever applied without configuration
