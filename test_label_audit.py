"""Regression cases independently identified during full catalog review."""
import json

import pytest

import apply_label_audit as audit


@pytest.fixture(scope="module")
def audited():
    decisions, records, _ = audit.build_audit()
    return decisions, records


@pytest.mark.parametrize("key,label", [
    ("r059|1042759|1000011054468004", "Incorrect"),  # oil instead of water
    ("r123|1042759|10553655750", "Incorrect"),  # sandwiches, not spread
    ("r065|29631686|22646327699", "Acceptable"),  # intervening words
    ("r142|29631686|1000040970948003", "Acceptable"),  # pack versus count parser error
    ("r151|29631686|22646303929", "Acceptable"),
    ("r009|1042759|1000037999605003", "Incorrect"),  # previous human error
    ("r079|29631686|1000030409614203", "Acceptable"),  # reordered flavor words
    ("r138|29631686|41511254172", "Incorrect"),  # lime versus strawberry
    ("r145|29631686|22646326552", "Incorrect"),  # fresh versus frozen
    ("r083|29631686|32760619640", "Needs clarification"),  # ambiguous oz
    ("r109|35802549|32929359730", "Needs clarification"),  # title/raw_size conflict
])
def test_observed_label_regressions(audited, key, label):
    assert audited[0][key]["reviewer_label"] == label


def test_complete_coverage_and_honest_provenance(audited):
    decisions, records = audited
    assert len(decisions) == len(records) == 1658
    assert len({d["request_id"] for d in decisions.values()}) == 150
    assert all(d["reviewed_by"] == "codex_ai_audit" for d in decisions.values())
    assert all(r["previous"] and r["evidence"] for r in records)


def test_materializer_rejects_changed_inputs(monkeypatch):
    monkeypatch.setattr(audit, "digest", lambda path: "changed")
    with pytest.raises(ValueError, match="Audit inputs changed"):
        audit.build_audit()


def test_auto_label_rerun_preserves_audited_decisions(audited, tmp_path, monkeypatch):
    import claude_auto_label as auto
    from benchmark_requests import REQUESTS
    # Include an old chat-seeded key, the path that formerly overwrote reviews.
    key = "r001|24325284|16915213943"
    preserved = {key: dict(audited[0][key])}
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(preserved))
    pools = tmp_path / "pools.json"
    pools.write_text(json.dumps([{"request_id": "r001", "candidates": [
        {"store_id": 24325284, "product_id": "16915213943"}]}]))
    monkeypatch.setattr(auto, "DECISIONS_PATH", path)
    monkeypatch.setattr(auto, "CANDIDATE_POOL_PATH", pools)
    monkeypatch.setattr(auto, "HUMAN_REVIEWED_FROM_CHAT", [
        ("r001", 24325284, "16915213943", "Acceptable")])
    monkeypatch.setattr(auto, "_load_catalog_by_key", lambda: {})
    monkeypatch.setattr(auto, "REQUESTS", REQUESTS[:1])
    monkeypatch.setattr(auto, "save_decisions_atomic", lambda data: path.write_text(json.dumps(data)))
    monkeypatch.setattr("sys.argv", ["claude_auto_label.py"])
    auto.main()
    assert json.loads(path.read_text()) == preserved
