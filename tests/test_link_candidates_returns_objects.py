"""Regression: linking candidates must hand back the candidates.

Found loading a real corpus through the CLI: `claim-link-candidates --json` returned
`{"claim_id":..., "intake_batch_id":..., "linked": <int>}` while `candidate-list --json`
returned `{"claim_id":..., "candidates":[...]}`. A loader that read `.get("candidates")`
from the link result got an int and crashed — the same key meaning two different things
across two commands about the same objects.

Two things follow. A command that links objects returns those objects, so the caller can go
straight on to rate them instead of re-listing the claim to find their ids. And it reports
matches as well as new links, so re-running describes the same set both times instead of
collapsing to an unhelpful `linked: 0` — the ids are exactly what a resumed loader needs.

The counts stay: nothing that read `linked` stopped working.

Offline: fake provider, no network.
"""

from __future__ import annotations

import json

from citevahti.agent import tools as agent_tools
from citevahti.claims import CandidateService, ClaimService
from citevahti.cli import main
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.pubmed import ProviderHit, ProviderSearchResult
from citevahti.state import CiteVahtiStore

_HITS = [
    ProviderHit(pmid="21714641", doi="10.1056/NEJMoa1102873", title="NLST"),
    ProviderHit(pmid="32004427", doi="10.1056/NEJMoa1911793", title="NELSON"),
]


class _Provider:
    name = "pubmed"

    def search(self, query, max_results=20, date_range=None, include_abstracts=False):
        return ProviderSearchResult(status="ok", hits=_HITS, count=len(_HITS),
                                    email_present=True, rate_tier="3rps")


def _seed(tmp_path):
    store = CiteVahtiStore(str(tmp_path))
    store.init()
    claim = ClaimService(store).add_claim("LDCT reduces lung-cancer mortality.", "effectiveness")
    batch = IntakeService(store, provider=_Provider(),
                          library_index=StaticLibraryIndex()).literature_search(
                              "ldct", question_id="q1")
    return store, claim.claim_id, batch.batch_id


def test_the_link_report_carries_the_linked_candidates(tmp_path):
    store, claim_id, batch_id = _seed(tmp_path)
    rep = CandidateService(store).link_from_intake(claim_id, batch_id)

    assert rep.linked == 2
    assert [c.title for c in rep.candidates] == ["NLST", "NELSON"]
    assert all(c.candidate_id for c in rep.candidates)
    # the same objects the claim now holds -- not a parallel, drifting list
    stored = {c.candidate_id for c in store.load_candidates(claim_id).candidates}
    assert {c.candidate_id for c in rep.candidates} == stored


def test_relinking_reports_the_same_candidates_not_an_empty_result(tmp_path):
    """A resumed loader re-links a batch it already linked. `linked: 0` is true but
    useless; the ids of the sources it asked about are what it needs."""
    store, claim_id, batch_id = _seed(tmp_path)
    svc = CandidateService(store)
    first = svc.link_from_intake(claim_id, batch_id)
    again = svc.link_from_intake(claim_id, batch_id)

    assert again.linked == 0 and again.skipped_duplicates == 2
    assert [c.candidate_id for c in again.candidates] == [c.candidate_id for c in first.candidates]
    assert again.total_candidates == 2          # and nothing was duplicated on disk


def test_a_record_id_filter_reports_only_those_candidates(tmp_path):
    store, claim_id, batch_id = _seed(tmp_path)
    wanted = store.load_intake(batch_id).hits[1].record_id
    rep = CandidateService(store).link_from_intake(claim_id, batch_id, record_ids=[wanted])

    assert rep.linked == 1
    assert [c.title for c in rep.candidates] == ["NELSON"]


# ---- the shape the loader crashed on --------------------------------------------------

def test_link_and_list_json_agree_on_what_candidates_means(tmp_path, capsys):
    """THE regression: one reader must handle both results. `candidates` is a list of
    candidate objects in each, keyed the same way."""
    store, claim_id, batch_id = _seed(tmp_path)
    capsys.readouterr()

    main(["--root", str(tmp_path), "claim-link-candidates", "--claim-id", claim_id,
          "--intake-batch-id", batch_id, "--json"])
    linked = json.loads(capsys.readouterr().out)

    main(["--root", str(tmp_path), "candidate-list", "--claim-id", claim_id, "--json"])
    listed = json.loads(capsys.readouterr().out)

    assert isinstance(linked["candidates"], list)          # was an int in `linked`
    assert [c["candidate_id"] for c in linked["candidates"]] \
        == [c["candidate_id"] for c in listed["candidates"]]
    assert linked["claim_id"] == listed["claim_id"]


def test_the_counts_are_still_there(tmp_path, capsys):
    """Additive: a script reading `linked` keeps working."""
    store, claim_id, batch_id = _seed(tmp_path)
    capsys.readouterr()
    main(["--root", str(tmp_path), "claim-link-candidates", "--claim-id", claim_id,
          "--intake-batch-id", batch_id, "--json"])
    res = json.loads(capsys.readouterr().out)

    assert res["linked"] == 2
    assert res["skipped_duplicates"] == 0
    assert res["total_candidates"] == 2
    assert res["intake_batch_id"] == batch_id


def test_the_agent_gets_ids_it_can_rate_without_re_listing(tmp_path):
    """The agent flow is link_candidates -> start_support_rating, and the second step
    needs a candidate_id. Compact identity only; the abstract stays behind list_candidates."""
    store, claim_id, batch_id = _seed(tmp_path)
    res = agent_tools.link_candidates(claim_id, batch_id, root=str(tmp_path))

    assert res["linked"] == 2
    ids = [c["candidate_id"] for c in res["candidates"]]
    assert len(ids) == 2 and all(ids)
    rating = agent_tools.start_support_rating(claim_id, ids[0], root=str(tmp_path))
    assert rating["rating_id"]
    assert "abstract" not in res["candidates"][0]
