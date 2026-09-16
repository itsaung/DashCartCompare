import json

from manual_review import DECISIONS_PATH, _key, generate, record_decision


def test_generate_creates_unreviewed_not_ok():
    rows, decisions = generate()
    for r in rows:
        d = decisions[_key(r["store_name"], r["product_id"])]
        # A freshly-generated row must never default to a positive verdict --
        # only record_decision() (an actual check) may set one.
        if d["reviewed_at"] is None:
            assert d["decision"] == "unreviewed"


def test_regenerating_preserves_existing_decisions():
    rows, decisions = generate()
    sample = rows[0]
    key = _key(sample["store_name"], sample["product_id"])
    record_decision(sample["store_name"], sample["product_id"], "verified", "test note")
    before = json.loads(DECISIONS_PATH.read_text())[key]

    # Regenerating (as if the script were re-run) must not overwrite this.
    generate()
    after = json.loads(DECISIONS_PATH.read_text())[key]
    assert after == before
    assert after["decision"] == "verified"

    # Clean up so this test is idempotent across runs.
    record_decision(sample["store_name"], sample["product_id"], "unreviewed", "")


def test_record_decision_requires_row_to_be_in_current_sample():
    import pytest

    with pytest.raises(KeyError):
        record_decision("NotAStore", "not-a-real-id", "verified")


def test_record_decision_rejects_invalid_decision_value():
    import pytest

    rows, _decisions = generate()
    sample = rows[0]
    with pytest.raises(ValueError):
        record_decision(sample["store_name"], sample["product_id"], "looks-fine-i-guess")
