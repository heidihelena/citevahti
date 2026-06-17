"""Conformance tests for the shared claim-text normalization (spec v1).

These vectors are the cross-tool contract — the SAME table is asserted in
MatchVahti's tests/run.mjs. If you change a vector here, change it there too, or
the two tools stop pooling into the same AtlasVahti cell. See
docs/CLAIM_NORMALIZATION.md.
"""

import hashlib

import pytest

from citevahti.util import normalize_claim_text, sha256_hex

# (input, expected normalized output) — byte-for-byte, must match the JS impl.
VECTORS = [
    ("LDCT reduces lung-cancer mortality.", "ldct reduces lung-cancer mortality."),
    ("  Multiple   spaces \t and \n tabs ", "multiple spaces and tabs"),
    ("MixedCASE Claim", "mixedcase claim"),
    ("Café", "café"),            # composed é (U+00E9)
    ("Café", "café"),           # decomposed e + combining acute → same as composed
    ("", ""),
]


@pytest.mark.parametrize("raw,expected", VECTORS)
def test_normalize_matches_vector(raw, expected):
    assert normalize_claim_text(raw) == expected


def test_nfc_composed_and_decomposed_hash_identically():
    # vectors 4 and 5: the whole point — same claim, different Unicode form, one hash
    assert sha256_hex(normalize_claim_text("Café")) == sha256_hex(normalize_claim_text("Café"))


def test_case_and_internal_whitespace_fold_into_one_hash():
    # the bug this spec fixes: case + internal spacing must not split the cell
    a = normalize_claim_text("LDCT  reduces   Mortality")
    b = normalize_claim_text("ldct reduces mortality")
    assert a == b == "ldct reduces mortality"


def test_handles_none_like_empty():
    assert normalize_claim_text(None) == ""


def test_hash_is_lowercase_hex_sha256():
    h = sha256_hex(normalize_claim_text("LDCT reduces lung-cancer mortality."))
    assert h == hashlib.sha256("ldct reduces lung-cancer mortality.".encode()).hexdigest()
    assert len(h) == 64 and h == h.lower()


def test_warehouse_uses_the_shared_normalizer():
    # the warehouse must hash via the shared spec, not its own private rule
    from citevahti import warehouse
    assert warehouse._norm_claim is normalize_claim_text
