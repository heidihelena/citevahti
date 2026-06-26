"""The update check is read-only, user-initiated, and must never crash or hit the live
network in tests. We drive it through an injected fake HttpClient so the suite stays
fully offline (same seam pattern as the probes)."""

from __future__ import annotations

import pytest

from citevahti import __version__
from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.update_check import _parse, check_update


class _FakeHttp:
    """Stand-in HttpClient. Either returns a canned response or raises to simulate an
    unreachable PyPI."""

    def __init__(self, *, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc
        self.calls: list[str] = []

    def get(self, url, headers=None, params=None):
        self.calls.append(url)
        if self._raise is not None:
            raise self._raise
        return self._response


def _pypi(version: str) -> HttpResponse:
    return HttpResponse(status_code=200, _json={"info": {"version": version}})


def test_parse_handles_clean_and_prerelease_versions():
    assert _parse("0.34.3") == (0, 34, 3)
    assert _parse("0.35.0rc1") == (0, 35, 0)   # stops at first non-digit per part
    assert _parse("1.0") < _parse("1.0.1")
    assert _parse("0.35.0") > _parse("0.34.9")


def test_up_to_date_when_latest_equals_current():
    http = _FakeHttp(response=_pypi("9.9.9"))
    r = check_update(http=http, current="9.9.9")
    assert r["checked"] is True
    assert r["update_available"] is False
    assert r["latest"] == "9.9.9"
    assert "up to date" in r["message"].lower()
    assert http.calls == ["https://pypi.org/pypi/citevahti/json"]


def test_update_available_when_pypi_is_newer():
    http = _FakeHttp(response=_pypi("9.9.9"))
    r = check_update(http=http, current="0.0.1")
    assert r["checked"] is True
    assert r["update_available"] is True
    assert r["latest"] == "9.9.9"
    # the message must give the non-technical user the actual next step
    assert "pip install -U citevahti" in r["message"]
    assert ".mcpb" in r["message"]


def test_older_pypi_version_is_not_flagged_as_an_update():
    # defensive: a yanked/older 'info.version' must never nag the user to "update" downward
    http = _FakeHttp(response=_pypi("0.0.1"))
    r = check_update(http=http, current="9.9.9")
    assert r["update_available"] is False


def test_network_failure_is_calm_not_a_crash():
    http = _FakeHttp(raise_exc=ProbeTransportError("connection refused"))
    r = check_update(http=http, current="1.2.3")
    assert r["checked"] is False          # couldn't check != something broke
    assert r["update_available"] is False
    assert "1.2.3" in r["message"]
    assert "couldn't reach pypi" in r["message"].lower()


def test_non_200_is_reported_without_raising():
    http = _FakeHttp(response=HttpResponse(status_code=503, text="busy"))
    r = check_update(http=http, current="1.2.3")
    assert r["checked"] is False
    assert "503" in r["message"]


def test_missing_version_field_is_handled():
    http = _FakeHttp(response=HttpResponse(status_code=200, _json={"info": {}}))
    r = check_update(http=http, current="1.2.3")
    assert r["checked"] is False
    assert r["latest"] is None


def test_defaults_to_the_real_running_version():
    # when current is omitted it reports the actual __version__ (so 'you have X' is honest)
    http = _FakeHttp(response=_pypi(__version__))
    r = check_update(http=http)
    assert r["current"] == __version__
    assert r["update_available"] is False
