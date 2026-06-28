"""Parse NCBI efetch (PubMed XML) into plain dicts. No network here."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    return "".join(el.itertext()).strip() or None


def _author_name(author: ET.Element) -> Optional[str]:
    collective = author.findtext("CollectiveName")
    if collective:
        return collective.strip()
    last = author.findtext("LastName")
    fore = author.findtext("ForeName") or author.findtext("Initials")
    if last and fore:
        return f"{fore} {last}".strip()
    return (last or fore or "").strip() or None


def _pub_date(article: ET.Element) -> tuple[Optional[str], Optional[int]]:
    pubdate = article.find(".//Journal/JournalIssue/PubDate")
    if pubdate is None:
        return None, None
    year = pubdate.findtext("Year")
    month = pubdate.findtext("Month")
    day = pubdate.findtext("Day")
    medline = pubdate.findtext("MedlineDate")
    year_int: Optional[int] = None
    if year and year.isdigit():
        year_int = int(year)
    elif medline:
        for tok in medline.split():
            if tok[:4].isdigit():
                year_int = int(tok[:4])
                break
    parts = [p for p in (year, month, day) if p]
    date_str = "-".join(parts) if parts else (medline or None)
    return date_str, year_int


def parse_efetch_xml(xml_text: str) -> list[dict]:
    """Return one dict per article with normalized bibliographic fields."""
    try:
        # TODO(security): switch to defusedxml for entity-expansion/XXE hardening — tracked as a follow-up.
        root = ET.fromstring(xml_text)  # noqa: S314 — defusedxml migration deferred (see TODO above)
    except ET.ParseError:
        return []
    out: list[dict] = []
    for art in root.findall(".//PubmedArticle"):
        citation = art.find("MedlineCitation")
        if citation is None:
            continue
        article = citation.find("Article")
        if article is None:
            continue
        pmid = citation.findtext("PMID")
        doi = None
        alt_pmid = None
        # Use ONLY the article's own id list (a direct child of PubmedData), never
        # `.//ArticleIdList` -- that descends into PubmedData/ReferenceList and would
        # pick up DOIs of *cited references* instead of this article's DOI.
        own_ids = art.find("PubmedData/ArticleIdList")
        if own_ids is not None:
            for aid in own_ids.findall("ArticleId"):
                idtype = aid.get("IdType")
                if idtype == "doi" and aid.text and doi is None:
                    doi = aid.text.strip()
                elif idtype == "pubmed" and aid.text and alt_pmid is None:
                    alt_pmid = aid.text.strip()
        # ELocationID (inside the Article element, not references) can also carry the DOI
        if doi is None:
            for eloc in article.findall("ELocationID"):
                if eloc.get("EIdType") == "doi" and eloc.text:
                    doi = eloc.text.strip()
                    break
        date_str, year = _pub_date(article)
        authors = [n for n in (_author_name(a) for a in article.findall(".//AuthorList/Author")) if n]
        abstract_parts = []
        for ab in article.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            txt = "".join(ab.itertext()).strip()
            if txt:
                abstract_parts.append(f"{label}: {txt}" if label else txt)
        out.append({
            "pmid": (pmid or alt_pmid or "").strip() or None,
            "doi": doi,
            "title": _text(article.find("ArticleTitle")) or "",
            "authors": authors,
            "journal": article.findtext(".//Journal/Title"),
            "publication_date": date_str,
            "year": year,
            "abstract": "\n".join(abstract_parts) or None,
        })
    return out
