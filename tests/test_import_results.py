"""import_results: RIS/CSV/BibTeX parsing, staging, dedupe, clean failure, audit."""

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
