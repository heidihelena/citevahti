"""Writing-assistance skills — helping a researcher turn vetted claims into prose.

These are advisory chat skills (run against the configured model from the Prompts & chat
panel), NOT the blinded claim-review flow. Each one keeps CiteVahti's discipline by
construction: it offers SUGGESTIONS the human reviews, never edits the manuscript silently,
never invents or drops a citation/citekey, and never claims the writing is correct, complete,
or publication-ready. CiteVahti checks citation support, not the truth or quality of prose.
"""

from __future__ import annotations

_GUARD = (
    "Offer this as a suggestion to review and edit — not a final or 'correct' version. "
    "Use ONLY the citations and citekeys (e.g. [@smith2020]) the researcher gives you; never "
    "invent, change, or drop a citation. Do not add claims or evidence they didn't provide, "
    "do not change a claim's meaning, and never assert that anything is proven, correct, or "
    "publication-ready. CiteVahti checks citation support, not truth or writing quality."
)


def draft_from_claims_prompt() -> str:
    return (
        "Help the researcher turn their vetted claims into a draft paragraph. They will paste "
        "one or more claims, each optionally with the citekey of its supporting source (like "
        "[@key]). Write a clear, plain academic paragraph that states each claim and places "
        "its [@citekey] immediately after the claim it supports. A claim with no citekey is "
        "left uncited — flag it as needing a source rather than inventing one.\n\n" + _GUARD)


def improve_structure_prompt() -> str:
    return (
        "Suggest a clearer structure for a paragraph the researcher pastes. Identify the topic "
        "sentence, propose a logical order for the supporting points, and note any claim left "
        "without a citation. Then offer a restructured version: reorder and tighten the prose, "
        "but keep every claim's meaning and every citation exactly where it belongs — move a "
        "[@citekey] only with the claim it supports.\n\n" + _GUARD)


def improve_transitions_prompt() -> str:
    return (
        "Suggest transitions for a paragraph the researcher pastes so the claims read as a "
        "coherent argument instead of a list. Add only connective wording (e.g. 'however', "
        "'consequently', 'in contrast'); keep each sentence's claim and each citation exactly "
        "as given. Show the transitions you'd add and why.\n\n" + _GUARD)


def spellcheck_prompt() -> str:
    return (
        "Flag likely spelling mistakes and obvious typos in the text the researcher pastes, "
        "listing each word with a suggested correction. This is advisory — the researcher "
        "decides. Do NOT 'correct' technical terms, drug or gene names, author names, or "
        "citekeys you are unsure about: list those as 'check' rather than a correction. Do not "
        "rewrite the content or comment on the writing's quality.")


def writing_skills() -> list[dict]:
    """The writing-assistance skills for the Prompts & chat panel (group 'Writing')."""
    return [
        {"name": "draft_from_claims", "label": "Draft from claims", "group": "Writing",
         "description": "Turn your vetted claims (with their citekeys) into a draft paragraph "
                        "to edit — uncited claims are flagged, never given an invented source.",
         "text": draft_from_claims_prompt()},
        {"name": "improve_structure", "label": "Improve structure", "group": "Writing",
         "description": "Suggest a clearer structure for a pasted paragraph (topic sentence, "
                        "order) — citations and claim meanings kept intact.",
         "text": improve_structure_prompt()},
        {"name": "improve_transitions", "label": "Improve transitions", "group": "Writing",
         "description": "Suggest connective wording so claims read as an argument, not a list "
                        "— content and citations unchanged.",
         "text": improve_transitions_prompt()},
        {"name": "check_spelling", "label": "Check spelling", "group": "Writing",
         "description": "Flag likely spelling mistakes with suggested corrections (advisory); "
                        "technical terms and citekeys are flagged to 'check', not changed.",
         "text": spellcheck_prompt()},
    ]
