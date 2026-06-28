"""`bib_sync` orchestration: scan -> extract -> resolve -> report -> export."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import __version__
from ..schemas.bibsync import BibSyncReport, ExportFormat, FileCitations
from ..schemas.common import LibrarySelector, Provenance
from ..state import CiteVahtiStore
from ..util import config_hash, utc_now_iso
from .extract import (
    SOURCE_EXTS,
    extract_keys_for_ext,
    parse_bib_keys,
    referenced_bib_paths,
)
from .provider import BibProvider, BibProviderUnavailable

_EXCLUDE_DIR_PARTS = {".git", ".citevahti", "__pycache__", ".pytest_cache"}
_GENERATED_NAMES = {"references.bib", "references.json"}
_FORMAT_EXT = {"bibtex": ".bib", "biblatex": ".bib", "csl-json": ".json"}

BBT_REMEDIATION = (
    "Better BibTeX is unavailable; cannot resolve or export citekeys. "
    "Install/enable Better BibTeX in Zotero (JSON-RPC at /better-bibtex/json-rpc)."
)


class BibSyncService:
    def __init__(self, provider: BibProvider, store: Optional[CiteVahtiStore] = None) -> None:
        self.provider = provider
        self.store = store

    # ---- scanning --------------------------------------------------------
    def _collect_sources(self, paths: list[str], output_dir: Optional[Path]) -> tuple[list[Path], list[Path]]:
        sources: list[Path] = []
        explicit_bibs: list[Path] = []
        seen: set[str] = set()

        def consider(p: Path) -> None:
            rp = p.resolve()
            if str(rp) in seen:
                return
            if any(part in _EXCLUDE_DIR_PARTS for part in rp.parts):
                return
            if p.name.startswith("."):
                return
            if output_dir is not None and output_dir.resolve() in rp.parents:
                return
            if p.name in _GENERATED_NAMES:
                return
            ext = p.suffix.lower()
            if ext == ".bib":
                seen.add(str(rp))
                explicit_bibs.append(p)
            elif ext in SOURCE_EXTS:
                seen.add(str(rp))
                sources.append(p)

        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                for child in sorted(p.rglob("*")):
                    if child.is_file():
                        consider(child)
            elif p.is_file():
                consider(p)
        sources.sort()
        return sources, explicit_bibs

    # ---- main ------------------------------------------------------------
    def run(self, paths: list[str], output_dir: Optional[str] = None,
            export_format: ExportFormat = "bibtex", include_cited_only: bool = True,
            make_master: bool = True, fail_on_orphans: bool = False,
            library: LibrarySelector = "personal") -> BibSyncReport:
        out_dir = Path(output_dir) if output_dir else None
        sources, explicit_bibs = self._collect_sources(paths, out_dir)

        report = BibSyncReport(
            scanned_files=[p.as_posix() for p in sources],
            provenance=self._provenance(paths, export_format, library),
        )

        # --- extract ------------------------------------------------------
        global_order: list[str] = []
        seen_keys: set[str] = set()
        bib_decls: list[Path] = list(explicit_bibs)
        for src in sources:
            text = src.read_text(encoding="utf-8", errors="replace")
            ext = src.suffix.lower()
            keys = extract_keys_for_ext(text, ext)
            report.citations_per_file.append(FileCitations(path=src.as_posix(), citekeys=keys))
            for k in keys:
                if k not in seen_keys:
                    seen_keys.add(k)
                    global_order.append(k)
            for rel in referenced_bib_paths(text, ext):
                cand = (src.parent / rel)
                if cand.name not in _GENERATED_NAMES:
                    bib_decls.append(cand)
        report.unique_citekeys = global_order

        # --- resolve (honest degradation if BBT absent) -------------------
        try:
            resolution = self.provider.resolve_many(global_order)
        except BibProviderUnavailable as exc:
            report.status = "degraded"
            report.error_code = "bbt_unavailable"
            report.remediation = BBT_REMEDIATION
            report.warnings.append(f"resolution skipped: {exc}")
            return report  # no fake bibliography, no invented resolution

        report.resolved_citekeys = [k for k in global_order if resolution.get(k)]
        report.orphan_citekeys = [k for k in global_order if not resolution.get(k)]

        # --- unused (from existing local .bib files) ----------------------
        report.bibliography_files, bib_keys = self._scan_bibliographies(bib_decls)
        report.unused_citekeys = [k for k in bib_keys if k not in seen_keys]

        if report.orphan_citekeys:
            report.warnings.append(f"{len(report.orphan_citekeys)} unresolved citekey(s) (orphans)")

        # --- fail_on_orphans: fail cleanly, write nothing -----------------
        if fail_on_orphans and report.orphan_citekeys:
            report.status = "failed"
            report.error_code = "orphans_present"
            report.remediation = ("Resolve or remove the orphan citekeys, or run without "
                                  "--fail-on-orphans.")
            return report

        # --- export -------------------------------------------------------
        if out_dir is not None and report.resolved_citekeys:
            self._write_exports(report, sources, out_dir, export_format,
                                 include_cited_only, make_master, resolution)
        return report

    # ---- helpers ---------------------------------------------------------
    def _scan_bibliographies(self, decls: list[Path]) -> tuple[list[str], list[str]]:
        files: list[str] = []
        keys: list[str] = []
        seen_files: set[str] = set()
        seen_keys: set[str] = set()
        for p in decls:
            try:
                rp = p.resolve()
            except OSError:
                continue
            if str(rp) in seen_files or not p.is_file():
                continue
            seen_files.add(str(rp))
            files.append(p.as_posix())
            for k in parse_bib_keys(p.read_text(encoding="utf-8", errors="replace")):
                if k not in seen_keys:
                    seen_keys.add(k)
                    keys.append(k)
        return files, keys

    def _write_exports(self, report: BibSyncReport, sources: list[Path], out_dir: Path,
                       export_format: str, include_cited_only: bool, make_master: bool,
                       resolution: dict[str, bool]) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = _FORMAT_EXT[export_format]
        resolved_set = set(report.resolved_citekeys)
        generated: list[str] = []
        used_names: set[str] = set()

        # per-file exports
        for fc, src in zip(report.citations_per_file, sources):
            keys = [k for k in fc.citekeys if k in resolved_set]
            if not keys:
                continue
            name = src.stem + ext
            i = 1
            while name in used_names:
                name = f"{src.stem}-{i}{ext}"
                i += 1
            used_names.add(name)
            target = out_dir / name
            target.write_text(self.provider.export(keys, export_format), encoding="utf-8")
            generated.append(target.as_posix())

        # merged master (cross-file dedup already done via global first-seen order)
        if make_master:
            master_name = "references" + ext
            master = out_dir / master_name
            master.write_text(self.provider.export(report.resolved_citekeys, export_format),
                              encoding="utf-8")
            generated.append(master.as_posix())

        report.generated_files = generated
        if self.store is not None and generated:
            entry = self.store.audit.append("bib_sync.write",
                                            {"generated": generated,
                                             "format": export_format,
                                             "resolved": len(report.resolved_citekeys)})
            report.audit_event_id = entry.hash

    def _provenance(self, paths, export_format, library) -> Provenance:
        return Provenance(
            tool="bib_sync", tool_version=__version__, ran_at=utc_now_iso(),
            config_hash=config_hash({"paths": list(paths), "format": export_format,
                                     "library": str(library)}),
            sources=[{"kind": "bbt", "detail": "citekey resolution + export"},
                     {"kind": "local_state", "detail": "source scan"}],
        )
