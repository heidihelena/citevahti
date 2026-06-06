"""bib_sync: extraction, resolution, orphans/unused, exports, honest degradation."""

from citevahti.bibsync import BibSyncService, StaticBibProvider
from citevahti.state import CiteVahtiStore

KNOWN = {
    "smith2020": "@article{smith2020, title={A}}",
    "jones2019": "@article{jones2019, title={B}}",
    "lee2021": "@article{lee2021, title={C}}",
}


def svc(known=KNOWN, available=True, store=None):
    return BibSyncService(StaticBibProvider(known, available), store)


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


# ---- scanning --------------------------------------------------------------
def test_scans_single_markdown(tmp_path):
    f = write(tmp_path / "a.md", "See [@smith2020].")
    r = svc().run([str(f)])
    assert r.scanned_files == [f.as_posix()]
    assert r.unique_citekeys == ["smith2020"]


def test_scans_directory_multiple_files(tmp_path):
    write(tmp_path / "01.md", "[@smith2020]")
    write(tmp_path / "02.md", "[@jones2019]")
    r = svc().run([str(tmp_path)])
    assert len(r.scanned_files) == 2
    assert set(r.unique_citekeys) == {"smith2020", "jones2019"}


def test_scans_quarto_qmd(tmp_path):
    f = write(tmp_path / "paper.qmd", "Result [@lee2021] holds.")
    r = svc().run([str(f)])
    assert r.unique_citekeys == ["lee2021"]


def test_scans_latex_tex(tmp_path):
    f = write(tmp_path / "main.tex", r"As shown \citep{smith2020}.")
    r = svc().run([str(f)])
    assert r.unique_citekeys == ["smith2020"]


# ---- extraction ------------------------------------------------------------
def test_pandoc_multi_citation(tmp_path):
    f = write(tmp_path / "a.md", "[@smith2020; @jones2019]")
    r = svc().run([str(f)])
    assert r.citations_per_file[0].citekeys == ["smith2020", "jones2019"]


def test_pandoc_suppressed_author(tmp_path):
    f = write(tmp_path / "a.md", "[-@smith2020, p. 33]")
    r = svc().run([str(f)])
    # locator stripped, key intact
    assert r.citations_per_file[0].citekeys == ["smith2020"]


def test_latex_multi_key(tmp_path):
    f = write(tmp_path / "a.tex", r"\citep{smith2020,jones2019}")
    r = svc().run([str(f)])
    assert r.citations_per_file[0].citekeys == ["smith2020", "jones2019"]


def test_latex_optional_args(tmp_path):
    f = write(tmp_path / "a.tex", r"\citep[see][12]{smith2020}")
    r = svc().run([str(f)])
    assert r.citations_per_file[0].citekeys == ["smith2020"]


def test_ignores_fenced_code(tmp_path):
    f = write(tmp_path / "a.md", "Real [@smith2020]\n\n```\n[@fakekey]\n```\n")
    r = svc().run([str(f)])
    assert r.unique_citekeys == ["smith2020"]


def test_ignores_inline_code(tmp_path):
    f = write(tmp_path / "a.md", "Use `[@fakecode]` but cite [@jones2019].")
    r = svc().run([str(f)])
    assert r.unique_citekeys == ["jones2019"]


def test_avoids_url_and_email_false_positives(tmp_path):
    f = write(tmp_path / "a.md",
              "Email me@example.com or http://x.com/@handle, then cite [@smith2020].")
    r = svc().run([str(f)])
    assert r.unique_citekeys == ["smith2020"]


def test_cross_file_dedup_first_seen_order(tmp_path):
    write(tmp_path / "01.md", "[@smith2020] then [@jones2019]")
    write(tmp_path / "02.md", "[@jones2019] then [@lee2021]")
    r = svc().run([str(tmp_path)])
    assert r.unique_citekeys == ["smith2020", "jones2019", "lee2021"]


# ---- resolution / orphans / degradation -----------------------------------
def test_unresolved_becomes_orphan(tmp_path):
    f = write(tmp_path / "a.md", "[@smith2020] and [@ghost1999]")
    r = svc().run([str(f)])
    assert r.resolved_citekeys == ["smith2020"]
    assert r.orphan_citekeys == ["ghost1999"]


def test_fail_on_orphans_fails_cleanly(tmp_path):
    f = write(tmp_path / "a.md", "[@ghost1999]")
    out = tmp_path / "out"
    r = svc().run([str(f)], output_dir=str(out), fail_on_orphans=True)
    assert r.status == "failed"
    assert r.error_code == "orphans_present"
    assert r.orphan_citekeys == ["ghost1999"]
    assert r.generated_files == []           # nothing written
    assert not out.exists()


def test_bbt_absent_degrades_honestly(tmp_path):
    f = write(tmp_path / "a.md", "[@smith2020]")
    r = svc(available=False).run([str(f)])
    assert r.status == "degraded"
    assert r.error_code == "bbt_unavailable"
    assert r.remediation and "Better BibTeX" in r.remediation
    assert r.resolved_citekeys == [] and r.generated_files == []


def test_fixture_citekeys_resolve_successfully(tmp_path):
    f = write(tmp_path / "a.md", "[@smith2020; @jones2019]")
    r = svc().run([str(f)])
    assert r.status == "ok"
    assert r.resolved_citekeys == ["smith2020", "jones2019"]
    assert r.orphan_citekeys == []


def test_no_invented_citekeys(tmp_path):
    f = write(tmp_path / "a.md", "[@smith2020] [@ghost1999]")
    out = tmp_path / "out"
    r = svc().run([str(f)], output_dir=str(out))
    assert set(r.resolved_citekeys) <= set(r.unique_citekeys)
    master = (out / "references.bib").read_text()
    assert "smith2020" in master and "ghost1999" not in master


# ---- exports + unused ------------------------------------------------------
def test_writes_per_file_and_master_exports(tmp_path):
    store = CiteVahtiStore(tmp_path / "proj")
    store.init()
    write(tmp_path / "a.md", "[@smith2020]")
    write(tmp_path / "b.md", "[@jones2019]")
    out = tmp_path / "out"
    r = svc(store=store).run([str(tmp_path / "a.md"), str(tmp_path / "b.md")],
                             output_dir=str(out))
    assert (out / "a.bib").exists() and (out / "b.bib").exists()
    assert (out / "references.bib").exists()
    assert set(r.generated_files) == {
        (out / "a.bib").as_posix(), (out / "b.bib").as_posix(),
        (out / "references.bib").as_posix()}
    assert r.audit_event_id is not None
    assert store.audit.verify() is True


def test_reports_unused_from_local_bib(tmp_path):
    write(tmp_path / "refs.bib",
          "@article{smith2020, title={A}}\n@article{unusedkey, title={Z}}\n")
    write(tmp_path / "paper.md",
          "---\nbibliography: refs.bib\n---\nSee [@smith2020].")
    r = svc().run([str(tmp_path / "paper.md")])
    assert "unusedkey" in r.unused_citekeys
    assert "smith2020" not in r.unused_citekeys


def test_multifile_thesis_after_reorg(tmp_path):
    # chapters moved into subdirs; a shared .bib; one orphan; one unused
    (tmp_path / "ch1").mkdir()
    (tmp_path / "ch2").mkdir()
    write(tmp_path / "refs.bib",
          "@article{smith2020,title={A}}\n@article{jones2019,title={B}}\n"
          "@article{stale1990,title={Old}}\n")
    write(tmp_path / "ch1" / "intro.qmd",
          "---\nbibliography: ../refs.bib\n---\n[@smith2020]")
    write(tmp_path / "ch2" / "methods.qmd",
          "---\nbibliography: ../refs.bib\n---\n[@jones2019] and [@ghost2000]")
    r = svc().run([str(tmp_path)])
    assert set(r.resolved_citekeys) == {"smith2020", "jones2019"}
    assert r.orphan_citekeys == ["ghost2000"]
    assert "stale1990" in r.unused_citekeys
