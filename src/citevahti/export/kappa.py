"""Inter-rater agreement statistics (pure Python, deterministic, no deps)."""

from __future__ import annotations

from collections import Counter
from typing import Optional


def raw_agreement(pairs: list[tuple[str, str]]) -> Optional[float]:
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(pairs: list[tuple[str, str]]):
    """Cohen's kappa for nominal two-rater pairs. Returns (result_dict, error)."""
    n = len(pairs)
    if n == 0:
        return {"value": None}, "no_pairs"
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    cats = set(ca) | set(cb)
    represented = len({v for pair in pairs for v in pair})
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in cats)
    if represented < 2 or (1 - pe) == 0:
        return {"value": None, "po": po, "categories": represented}, "insufficient_variation"
    return {"value": (po - pe) / (1 - pe), "po": po, "pe": pe}, None


def weighted_kappa(pairs: list[tuple[str, str]], ordinals: dict[str, int],
                   weights: str = "quadratic"):
    """Ordinal weighted kappa. ``ordinals`` maps label -> rank (missing-like
    labels must be excluded by the caller). Returns (result_dict, error)."""
    labels = sorted(ordinals, key=lambda lbl: ordinals[lbl])
    k = len(labels)
    n = len(pairs)
    if n == 0:
        return {"value": None, "weights": weights}, "no_pairs"
    if k < 2:
        return {"value": None, "weights": weights}, "insufficient_variation"
    order = {lbl: i for i, lbl in enumerate(labels)}

    def w(i: int, j: int) -> float:
        if weights == "linear":
            return abs(i - j) / (k - 1)
        return (i - j) ** 2 / ((k - 1) ** 2)

    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    do = sum(w(order[a], order[b]) for a, b in pairs) / n
    de = sum((ca.get(la, 0) / n) * (cb.get(lb, 0) / n) * w(order[la], order[lb])
             for la in labels for lb in labels)
    if de == 0:
        return {"value": None, "weights": weights}, "insufficient_variation"
    return {"value": 1 - do / de, "weights": weights}, None
