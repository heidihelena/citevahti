"""Check-a-paragraph: the everyday in-writing loop. Paste a snippet → each sentence is
matched to a vetted claim (reviewed), a claim that needs attention, or flagged new."""

from citevahti.demo import build
from citevahti.report.paragraph import check_paragraph
from citevahti.state import CiteVahtiStore


def test_check_paragraph_classifies_vetted_attention_and_new(tmp_path):
    build(tmp_path)                       # demo: accept (accepted) + needs_second_review (review_needed) + …
    store = CiteVahtiStore(tmp_path)
    para = (
        "Structured telephone follow-up reduces avoidable readmissions after day surgery. "
        "Nurse-led virtual clinics shorten the time to wound-complication detection. "
        "Quantum entanglement cures every cancer overnight in all patients.")
    c = check_paragraph(store, para)
    assert c.total == 3
    assert any(s.status == "reviewed" for s in c.sentences)    # the accepted demo claim
    assert any(s.status == "attention" for s in c.sentences)   # the review-needed demo claim
    assert any(s.status == "new" for s in c.sentences)         # the made-up sentence
    for s in c.sentences:
        if s.status == "attention":
            assert s.reason and s.action                       # why + next action
        if s.status == "reviewed":
            assert s.claim_id and s.state


def test_check_paragraph_empty_is_safe(tmp_path):
    build(tmp_path)
    c = check_paragraph(CiteVahtiStore(tmp_path), "")
    assert c.total == 0 and c.sentences == []
