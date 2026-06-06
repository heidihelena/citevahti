"""Probe-before-capability: probes report liveness; gating raises with remediation."""

import pytest

from citevahti.probe import run_probes
from citevahti.probe.probe import CapabilityUnavailable


def test_all_capabilities_available_when_healthy(healthy_client):
    report = run_probes(healthy_client)
    assert report.summary() == {"zotero_api": True, "bbt_ready": True, "bbt_cayw": True}
    assert report.results["zotero_api"].version == "9.0.4"
    # require() returns the result, does not raise.
    assert report.require("bbt_ready").available is True


def test_unreachable_endpoints_report_remediation(dead_client):
    report = run_probes(dead_client)
    assert report.summary() == {"zotero_api": False, "bbt_ready": False, "bbt_cayw": False}
    for name in ("zotero_api", "bbt_ready", "bbt_cayw"):
        r = report.results[name]
        assert r.remediation  # non-empty remediation string


def test_require_raises_before_using_unavailable_capability(dead_client):
    report = run_probes(dead_client)
    with pytest.raises(CapabilityUnavailable) as exc:
        report.require("zotero_api")
    assert "remediation" not in str(exc.value).lower() or "Zotero" in str(exc.value)


def test_require_unknown_capability_is_never_assumed(healthy_client):
    report = run_probes(healthy_client)
    with pytest.raises(CapabilityUnavailable):
        report.require("pubmed")  # never probed -> never assumed available
