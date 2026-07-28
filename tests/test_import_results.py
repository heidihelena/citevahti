"""import_results: RIS/CSV/BibTeX parsing, staging, dedupe, clean failure, audit."""

from citevahti.claims import CandidateService, ClaimService
from citevahti.intake import IntakeService, StaticLibraryIndex
from citevahti.intake.manual import parse_bibtex, parse_csv, parse_ris
from citevahti.state import CiteVahtiStore

RIS = """TY  - JOUR
TI  - A randomized trial of X
AU  - Smith, Jane
AU  - Doe, John
JO  - Journal of Tests
DO  - 10.1/ris-doi
PY  - 2021
AN  - 12345678
ER  -
"""

CSV = """title,doi,pmid,year,authors,journal
A CSV study,10.1/csv-doi,87654321,2019,Smith; Doe,J CSV
"""

BIBTEX = """@article{key1,
  title = {A BibTeX study},
  author = {Smith, Jane and Doe, John},
  journal = {J Bib},
  doi = {10.1/bib-doi},
  year = {2018},
  pmid = {11112222}
}
"""


def service(tmp_path, library_index=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return IntakeService(store, library_index=library_index), store


# ---- parsers ---------------------------------------------------------------
def test_parse_ris_fields():
    rec = parse_ris(RIS)[0]
    assert rec["doi"] == "10.1/ris-doi" and rec["pmid"] == "12345678"
    assert rec["year"] == 2021 and "randomized trial" in rec["title"]
    assert rec["authors"] == ["Smith, Jane", "Doe, John"]


def test_parse_csv_fields():
    rec = parse_csv(CSV)[0]
    assert rec["doi"] == "10.1/csv-doi" and rec["pmid"] == "87654321"
    assert rec["year"] == 2019 and rec["authors"] == ["Smith", "Doe"]


def test_parse_bibtex_fields():
    rec = parse_bibtex(BIBTEX)[0]
    assert rec["doi"] == "10.1/bib-doi" and rec["pmid"] == "11112222"
    assert rec["year"] == 2018 and len(rec["authors"]) == 2


# ---- staging ---------------------------------------------------------------
def test_imports_ris_stages_records(tmp_path):
    svc, store = service(tmp_path)
    rec = svc.import_results({"text": RIS}, "ris", source_label="manual ris")
    assert rec.status == "ok" and rec.provider == "manual"
    assert rec.hits[0].doi == "10.1/ris-doi" and rec.hits[0].decision is None
    assert rec.source_format == "ris" and rec.source_hash
    assert store.list_intake() == [rec.batch_id]


def test_imports_csv_and_bibtex(tmp_path):
    svc, _ = service(tmp_path)
    assert svc.import_results({"text": CSV}, "csv").hits[0].pmid == "87654321"
    assert svc.import_results({"text": BIBTEX}, "bibtex").hits[0].doi == "10.1/bib-doi"


def test_import_dedupes_against_prior_intake(tmp_path):
    svc, _ = service(tmp_path)
    svc.import_results({"text": RIS}, "ris", question_id="q1")
    rec2 = svc.import_results({"text": RIS}, "ris", question_id="q2")
    assert rec2.hits[0].dedupe_status == "already_in_prior_intake"


def test_import_dedupes_against_library(tmp_path):
    svc, _ = service(tmp_path, library_index=StaticLibraryIndex(dois=["10.1/ris-doi"]))
    rec = svc.import_results({"text": RIS}, "ris")
    assert rec.hits[0].dedupe_status == "already_in_library"


def test_parse_failure_fails_cleanly_no_write(tmp_path):
    svc, store = service(tmp_path)
    rec = svc.import_results({"text": "this is not RIS at all"}, "ris")
    assert rec.status == "degraded" and rec.error_code == "parse_error"
    assert store.list_intake() == []          # no partial write


def test_import_audit_event_and_verify(tmp_path):
    svc, store = service(tmp_path)
    rec = svc.import_results({"text": RIS}, "ris")
    assert rec.audit_event_id is not None
    assert "intake.write" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True


# ---- abstracts -------------------------------------------------------------
# The abstract is all the blinded rater and the panel see beyond the title, so a
# parser that reads a source's abstract tag and drops it produces title-only
# judgements that look like ordinary ones.
RIS_WITH_ABSTRACT = """TY  - JOUR
TI  - A randomized trial of X
AU  - Smith, Jane
DO  - 10.1/ris-abs
PY  - 2021
AB  - Background: X was compared with placebo in 400 adults.
Results: X reduced the primary endpoint by 12%.
ER  -
"""

RIS_N2_ABSTRACT = """TY  - JOUR
TI  - A trial exported with N2
DO  - 10.1/ris-n2
N2  - The summary tag some exporters use instead of AB.
ER  -
"""

RIS_BOTH_ABSTRACT_TAGS = """TY  - JOUR
TI  - A trial exported with both tags
DO  - 10.1/ris-both
AB  - The same abstract, twice.
N2  - The same abstract, twice.
ER  -
"""

CSV_WITH_ABSTRACT = """title,doi,abstract
A CSV study,10.1/csv-abs,We enrolled 200 patients and found no difference.
A CSV study without one,10.1/csv-none,
"""

CSV_ZOTERO_HEADER = """Title,DOI,Abstract Note
A Zotero export,10.1/zot-abs,Zotero names the column Abstract Note.
"""

BIBTEX_WITH_ABSTRACT = """@article{key1,
  title = {A BibTeX study},
  doi = {10.1/bib-abs},
  year = {2018},
  abstract = {A cohort of 1200 was followed for five years.}
}
"""


def test_parse_ris_reads_the_ab_tag_and_its_wrapped_lines():
    rec = parse_ris(RIS_WITH_ABSTRACT)[0]
    assert rec["abstract"] == ("Background: X was compared with placebo in 400 adults. "
                               "Results: X reduced the primary endpoint by 12%.")


def test_parse_ris_reads_n2_when_that_is_the_exporters_tag():
    assert parse_ris(RIS_N2_ABSTRACT)[0]["abstract"] == \
        "The summary tag some exporters use instead of AB."


def test_parse_ris_does_not_double_an_abstract_carried_by_both_tags():
    assert parse_ris(RIS_BOTH_ABSTRACT_TAGS)[0]["abstract"] == "The same abstract, twice."


def test_parse_ris_without_an_abstract_tag_yields_none():
    assert parse_ris(RIS)[0]["abstract"] is None


def test_parse_csv_reads_an_abstract_column():
    recs = parse_csv(CSV_WITH_ABSTRACT)
    assert recs[0]["abstract"] == "We enrolled 200 patients and found no difference."
    assert recs[1]["abstract"] is None            # an empty cell is no abstract, not ""


def test_parse_csv_reads_zoteros_abstract_note_header():
    assert parse_csv(CSV_ZOTERO_HEADER)[0]["abstract"] == \
        "Zotero names the column Abstract Note."


def test_parse_bibtex_reads_the_abstract_field():
    assert parse_bibtex(BIBTEX_WITH_ABSTRACT)[0]["abstract"] == \
        "A cohort of 1200 was followed for five years."


def test_abstract_reaches_the_staged_hit_and_then_the_candidate(tmp_path):
    svc, store = service(tmp_path)
    batch = svc.import_results({"text": RIS_WITH_ABSTRACT}, "ris")
    assert batch.hits[0].abstract.startswith("Background: X was compared")

    claim = ClaimService(store).add_claim("X reduces the primary endpoint.", "effectiveness")
    CandidateService(store).link_from_intake(claim.claim_id, batch.batch_id)
    cand = store.load_candidates(claim.claim_id).candidates[0]
    assert cand.abstract == batch.hits[0].abstract   # what the blinded rater will read


def test_import_warns_when_staged_records_have_no_abstract(tmp_path):
    svc, _ = service(tmp_path)
    rec = svc.import_results({"text": CSV_WITH_ABSTRACT}, "csv")
    assert rec.status == "ok"                        # a fact about the corpus, not a failure
    assert len(rec.warnings) == 1
    assert "1 of 2 staged records carry an abstract" in rec.warnings[0]
    assert "title alone" in rec.warnings[0]


def test_import_does_not_warn_when_every_record_has_an_abstract(tmp_path):
    svc, _ = service(tmp_path)
    assert svc.import_results({"text": RIS_WITH_ABSTRACT}, "ris").warnings == []
