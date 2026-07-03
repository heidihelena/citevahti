"""Shared fixtures: a fake HTTP client and a small but complete rating frame."""

from __future__ import annotations

from typing import Any, Optional

import pytest


@pytest.fixture(autouse=True)
def _isolate_host_state(tmp_path, monkeypatch):
    """No test may touch the real user's log or runtime-handshake directories.

    Running the suite on a machine where CiteVahti.app was live wrote pytest engine
    runs straight into the user's ``~/Library/Logs/CiteVahti/engine.log``
    (2026-07-02). Individual tests already isolate what they know they use; this is
    the backstop for the path a test doesn't realize it exercises. Tests that assert
    on these locations simply monkeypatch over it, as before.
    """
    monkeypatch.setattr("citevahti.paths.log_dir", lambda: tmp_path / "_host_logs")
    monkeypatch.setattr("citevahti.paths.runtime_dir", lambda: tmp_path / "_host_runtime")

from citevahti.probe.client import HttpResponse, ProbeTransportError
from citevahti.schemas.common import ItemRef
from citevahti.schemas.frame import Domain, Frame, Level, Outcome, Scheme, Study
from citevahti.schemas.rating import (
    Adjudication,
    AIProvenance,
    AIRating,
    Comparison,
    HumanRating,
    RatingRecord,
    Subject,
)


class FakeHttpClient:
    """Routes by (method, url-substring) to canned HttpResponses or raises."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, str, Any]] = []

    def _resolve(self, method: str, url: str) -> HttpResponse:
        for (m, frag), value in self.routes.items():
            if m == method and frag in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise ProbeTransportError(f"no route for {method} {url}")

    def get(self, url, headers=None, params=None) -> HttpResponse:
        self.requests.append(("GET", url, params))
        return self._resolve("GET", url)

    def post(self, url, json=None, headers=None) -> HttpResponse:
        self.requests.append(("POST", url, json))
        return self._resolve("POST", url)

    def urls(self) -> list[str]:
        return [u for _, u, _ in self.requests]


@pytest.fixture
def healthy_client() -> FakeHttpClient:
    return FakeHttpClient({
        ("GET", "/api/"): HttpResponse(200, headers={"zotero-version": "9.0.4"}),
        ("POST", "json-rpc"): HttpResponse(200, _json={"jsonrpc": "2.0", "result": True, "id": 1}),
        ("GET", "cayw"): HttpResponse(200, text=""),
    })


@pytest.fixture
def dead_client() -> FakeHttpClient:
    return FakeHttpClient({
        ("GET", "/api/"): ProbeTransportError("connection refused"),
        ("POST", "json-rpc"): ProbeTransportError("connection refused"),
        ("GET", "cayw"): ProbeTransportError("connection refused"),
    })


@pytest.fixture
def frame() -> Frame:
    return Frame(
        frame_id="frame_pico1",
        frame_version="1.0.0",
        created_at="2026-06-01T00:00:00+00:00",
        outcomes=[Outcome(outcome_id="o_mortality", label="All-cause mortality")],
        studies=[Study(study_id="s_smith2020", item=ItemRef(zotero_key="ABC123"))],
        schemes=[
            Scheme(
                scheme_id="grade_certainty", kind="GRADE", unit="outcome",
                levels=[
                    Level(value="High", ordinal=4), Level(value="Moderate", ordinal=3),
                    Level(value="Low", ordinal=2), Level(value="Very Low", ordinal=1),
                ],
            ),
            Scheme(
                scheme_id="rob2", kind="RoB2", unit="study",
                domains=[Domain(domain_id="d1", label="Randomization")],
                levels=[
                    Level(value="Low", ordinal=3), Level(value="Some concerns", ordinal=2),
                    Level(value="High", ordinal=1),
                ],
            ),
            Scheme(
                scheme_id="robins_i", kind="ROBINS-I", unit="study",
                levels=[
                    Level(value="Low", ordinal=5), Level(value="Moderate", ordinal=4),
                    Level(value="Serious", ordinal=3), Level(value="Critical", ordinal=2),
                    Level(value="No information", ordinal=None, missing_like=True),
                ],
            ),
        ],
    )


def make_ai_provenance(model_id: str = "claude-opus-4-8",
                       model_snapshot: str = "2026-05-01") -> AIProvenance:
    return AIProvenance(
        provider="anthropic", model_id=model_id, model_snapshot=model_snapshot,
        prompt_template_version="v1", prompt_hash="deadbeef", config_hash="cafef00d",
        rated_at="2026-06-01T01:00:00+00:00",
    )


def make_grade_rating(
    rating_id: str = "r1",
    human_value: Optional[str] = "Moderate",
    ai_value: Optional[str] = "Moderate",
    ai_abstained: bool = False,
    status: Optional[str] = None,
    final_value: Optional[str] = None,
    event: Optional[str] = None,
    decided_by: Optional[str] = None,
) -> RatingRecord:
    human = None
    if human_value is not None:
        human = HumanRating(value=human_value, committed_at="2026-06-01T00:30:00+00:00",
                            committed_by="rater_a", locked=True)
    ai = None
    if ai_value is not None or ai_abstained:
        ai = AIRating(value=None if ai_abstained else ai_value, abstained=ai_abstained,
                      provenance=make_ai_provenance())
    return RatingRecord(
        rating_id=rating_id, frame_id="frame_pico1", frame_version="1.0.0",
        scheme_id="grade_certainty", subject=Subject(outcome_id="o_mortality"),
        human_rating=human, ai_rating=ai,
        comparison=Comparison(status=status),
        adjudication=Adjudication(final_value=final_value, event=event, decided_by=decided_by),
    )
