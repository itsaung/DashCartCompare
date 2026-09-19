import pytest

from apply_photo_review import build_review


@pytest.fixture(scope="module")
def review():
    return build_review()


def test_only_uncertain_pairs_change_and_keep_honest_evidence(review):
    before, after, records = review
    assert len(records) == 114
    assert len(before) == len(after) == 1658
    assert all(d["reviewer_label"] != "Needs clarification" for d in after.values())
    for key, old in before.items():
        new = after[key]
        if old["reviewer_label"] != "Needs clarification":
            assert new == old
        else:
            assert new["photo_evidence"]["photo_sha256"]
            assert new["reviewed_by"] == "codex_photo_review"
            if new["is_best_guess"]:
                assert new["conservative_label"] == "Needs clarification"


@pytest.mark.parametrize("key,label,guess", [
    ("r073|29631686|1000030409614136", "Acceptable", False),  # photo: 20 ct / 23 oz
    ("r141|29631686|1000032999710119", "Incorrect", False),  # photo: 10 ct soft taco
    ("r007|1742136|11194800448", "Acceptable", False),  # grass fed, unsalted, 2 x4 oz sticks
    ("r109|35802549|32929359730", "Incorrect", False),  # two connected cups
    ("r098|35802549|30994828628", "Incorrect", False),  # photo: 22 oz, request: 9 oz
    ("r099|24325284|21040431450", "Incorrect", True),  # photo/title count conflict
    ("r022|1742136|10109224134", "Incorrect", True),  # photo/title multipack conflict
    ("r083|1042759|8776540508", "Acceptable", True),  # assumed fluid ounces in request
    ("r129|35802549|30994848258", "Acceptable", False),  # photo: two salmon fillets
])
def test_readable_package_evidence_and_uncertain_intent(review, key, label, guess):
    decision = review[1][key]
    assert decision["reviewer_label"] == label
    assert decision["is_best_guess"] is guess


def test_photo_and_mapping_changes_invalidate_review(monkeypatch):
    monkeypatch.setattr("apply_photo_review.sha", lambda path: "changed")
    with pytest.raises(ValueError, match="Photo audit input changed"):
        build_review()
