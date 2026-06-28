"""Deterministic RIS / CSV / BibTeX parsing for manual import.

Each parser returns a list of plain dicts (pmid, doi, title, authors, journal,
year). Malformed input raises ManualParseError so the caller can fail cleanly
with no partial write.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Optional


class ManualParseError(Exception):
    code = "parse_error"


def _year(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"\d{4}", str(value))
    return int(m.group(0)) if m else None


# ---- RIS -------------------------------------------------------------------
def parse_ris(text: str) -> list[dict]:
    if "TY  -" not in text and "TY -" not in text:
        raise ManualParseError("not RIS: no TY tag found")
    records: list[dict] = []
    cur: Optional[dict] = None
    authors: list[str] = []
    for raw in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])\s{0,2}-\s?(.*)$", raw)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"title": "", "authors": [], "journal": None, "doi": None,
                   "pmid": None, "year": None, "publication_date": None}
            authors = []
        elif cur is None:
            continue
        elif tag in ("TI", "T1"):
            cur["title"] = val
        elif tag == "AU":
            authors.append(val)
        elif tag in ("JO", "JF", "T2"):
            cur["journal"] = val
        elif tag == "DO":
            cur["doi"] = val
        elif tag in ("PY", "Y1"):
            cur["year"] = _year(val)
        elif tag == "AN" and val.isdigit():
            cur["pmid"] = val
        elif tag == "ER":
            cur["authors"] = authors
            records.append(cur)
            cur, authors = None, []
    if cur is not None:  # unterminated record
        cur["authors"] = authors
        records.append(cur)
    if not records:
        raise ManualParseError("no RIS records parsed")
    return records


# ---- CSV -------------------------------------------------------------------
_CSV_ALIASES = {
    "pmid": "pmid", "pubmed_id": "pmid", "pubmed id": "pmid",
    "doi": "doi",
    "title": "title", "article title": "title",
    "authors": "authors", "author": "authors",
    "journal": "journal", "source": "journal",
    "year": "year", "publication year": "year", "pubyear": "year",
}


def parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ManualParseError("not CSV: no header row")
    norm = {fn: _CSV_ALIASES.get((fn or "").strip().lower()) for fn in reader.fieldnames}
    if not any(norm.values()):
        raise ManualParseError("CSV has no recognizable columns")
    out: list[dict] = []
    for row in reader:
        rec: dict[str, Any] = {"title": "", "authors": [], "journal": None, "doi": None,
                               "pmid": None, "year": None, "publication_date": None}
        for fn, value in row.items():
            key = norm.get(fn)
            if not key or value is None:
                continue
            value = value.strip()
            if key == "authors":
                rec["authors"] = [a.strip() for a in re.split(r"[;]", value) if a.strip()]
            elif key == "year":
                rec["year"] = _year(value)
            else:
                rec[key] = value
        if rec["title"] or rec["doi"] or rec["pmid"]:
            out.append(rec)
    if not out:
        raise ManualParseError("no CSV records parsed")
    return out


# ---- BibTeX ----------------------------------------------------------------
_BIB_ENTRY = re.compile(r"@\w+\s*\{[^,]*,(.*?)\n\}", re.DOTALL)
_BIB_FIELD = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE | re.DOTALL)


def parse_bibtex(text: str) -> list[dict]:
    if "@" not in text:
        raise ManualParseError("not BibTeX: no @ entries")
    out: list[dict] = []
    for body in _BIB_ENTRY.findall(text):
        fields = {k.lower(): re.sub(r"\s+", " ", v).strip()
                  for k, v in _BIB_FIELD.findall(body)}
        if not fields:
            continue
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        out.append({
            "title": fields.get("title", ""),
            "authors": authors,
            "journal": fields.get("journal") or fields.get("journaltitle"),
            "doi": fields.get("doi"),
            "pmid": fields.get("pmid"),
            "year": _year(fields.get("year") or fields.get("date")),
            "publication_date": fields.get("date") or fields.get("year"),
        })
    if not out:
        raise ManualParseError("no BibTeX records parsed")
    return out


def parse_manual(text: str, fmt: str) -> list[dict]:
    if fmt == "ris":
        return parse_ris(text)
    if fmt == "csv":
        return parse_csv(text)
    if fmt == "bibtex":
        return parse_bibtex(text)
    raise ManualParseError(f"unsupported format {fmt!r}")
