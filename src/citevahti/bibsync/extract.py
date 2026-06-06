"""Citation + bibliography extraction.

Pandoc and LaTeX citekeys are extracted in first-seen order, after masking out
code (fenced blocks, inline spans) and LaTeX comments so that URLs, emails, and
code do not produce false positives. Keys are never altered: locators,
prefixes/suffixes and optional arguments are stripped around the key, not from
it.
"""

from __future__ import annotations

import re

MARKDOWN_EXTS = {".md", ".qmd", ".rmd"}
LATEX_EXTS = {".tex"}
SOURCE_EXTS = MARKDOWN_EXTS | LATEX_EXTS

# A citekey: starts alphanumeric/_, internal punctuation allowed, ends
# alphanumeric/_ (so trailing '.' ',' etc. are never captured into the key).
_KEY = r"[A-Za-z0-9_](?:[A-Za-z0-9_:.#$%&+?/~<>-]*[A-Za-z0-9_])?"

# Pandoc: @key / -@key, at a citation boundary (not preceded by word char, '@',
# '/', '.', '-' -> rules out emails like a@b and url handles like /@h).
_PANDOC_RE = re.compile(r"(?<![\w@/.\-])-?@(" + _KEY + r")")

_LATEX_CMDS = (
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "autocite", "parencite", "textcite", "footcite", "smartcite", "supercite",
    "nocite",
)
# \cmd*?[opt][opt]{k1, k2}
_LATEX_RE = re.compile(
    r"\\(?:" + "|".join(_LATEX_CMDS) + r")\*?(?:\s*\[[^\]]*\])*\s*\{([^}]*)\}"
)

_FENCED = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,}).*?\n.*?\2", re.DOTALL)
_INLINE_CODE = re.compile(r"`+[^`\n]*`+")
_TEX_COMMENT = re.compile(r"(?<!\\)%[^\n]*")


def _mask_markdown_code(text: str) -> str:
    text = _FENCED.sub(lambda m: m.group(1), text)
    text = _INLINE_CODE.sub(" ", text)
    return text


def _strip_tex_comments(text: str) -> str:
    return _TEX_COMMENT.sub("", text)


def _ordered_unique(keys) -> list[str]:
    seen: dict[str, None] = {}
    for k in keys:
        if k not in seen:
            seen[k] = None
    return list(seen.keys())


def extract_pandoc_keys(text: str) -> list[str]:
    """First-seen-ordered Pandoc citekeys, code masked out."""
    cleaned = _mask_markdown_code(text)
    return _ordered_unique(m.group(1) for m in _PANDOC_RE.finditer(cleaned))


def extract_latex_keys(text: str) -> list[str]:
    """First-seen-ordered LaTeX citekeys (handles multi-key + optional args)."""
    cleaned = _strip_tex_comments(text)
    out: list[str] = []
    for m in _LATEX_RE.finditer(cleaned):
        for raw in m.group(1).split(","):
            key = raw.strip()
            if key:
                out.append(key)
    return _ordered_unique(out)


def extract_keys_for_ext(text: str, ext: str) -> list[str]:
    ext = ext.lower()
    if ext in LATEX_EXTS:
        return extract_latex_keys(text)
    return extract_pandoc_keys(text)


# ---- existing-bibliography discovery (for unused detection) --------------
_YAML_BIB_SCALAR = re.compile(r"^bibliography:\s*(.+?)\s*$", re.MULTILINE)
_YAML_BIB_LIST_ITEM = re.compile(r"^\s*-\s*(.+?)\s*$", re.MULTILINE)
_TEX_BIBLIOGRAPHY = re.compile(r"\\bibliography\{([^}]*)\}")
_TEX_ADDBIB = re.compile(r"\\addbibresource\{([^}]*)\}")
_BIB_ENTRY = re.compile(r"@\w+\s*\{\s*([^,\s}]+)\s*,", re.MULTILINE)


def _front_matter(text: str) -> str | None:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return None


def referenced_bib_paths(text: str, ext: str) -> list[str]:
    """Bibliography file paths declared by a source file (relative strings)."""
    ext = ext.lower()
    paths: list[str] = []
    if ext in MARKDOWN_EXTS:
        fm = _front_matter(text)
        if fm:
            m = _YAML_BIB_SCALAR.search(fm)
            if m:
                val = m.group(1).strip()
                if val.startswith("["):
                    for part in val.strip("[]").split(","):
                        p = part.strip().strip("'\"")
                        if p:
                            paths.append(p)
                elif val:
                    paths.append(val.strip("'\""))
            else:
                # block list under "bibliography:"
                bm = re.search(r"^bibliography:\s*$(.*?)(^\S|\Z)",
                               fm, re.MULTILINE | re.DOTALL)
                if bm:
                    for im in _YAML_BIB_LIST_ITEM.finditer(bm.group(1)):
                        paths.append(im.group(1).strip().strip("'\""))
    if ext in LATEX_EXTS:
        for m in _TEX_BIBLIOGRAPHY.finditer(text):
            for part in m.group(1).split(","):
                p = part.strip()
                if p:
                    paths.append(p if p.endswith(".bib") else p + ".bib")
        for m in _TEX_ADDBIB.finditer(text):
            for part in m.group(1).split(","):
                p = part.strip()
                if p:
                    paths.append(p)
    return paths


def parse_bib_keys(bib_text: str) -> list[str]:
    """Entry keys defined in a .bib file."""
    return _ordered_unique(m.group(1) for m in _BIB_ENTRY.finditer(bib_text))
