"""Tests for audit_size_tolerance.py's detection logic. Small hand-built
fixtures with an injected violation, to prove the scan actually catches
something -- not just that it trivially passes on clean data."""
from audit_size_tolerance import find_size_tolerance_violations


def _request(request_id, text="15 oz cereal", size="15 oz", size_any=False):
    substitutions = {"size": "any"} if size_any else {}
    return {
        "request_id": request_id, "text": text,
        "expected": {"brand": None, "variant": None, "size": size, "allowed_substitutions": substitutions},
    }


def _row(raw_size, raw_title="Some Cereal"):
    return {"raw_size": raw_size, "raw_title": raw_title}


def test_flags_a_same_unit_tolerance_reliant_acceptable():
    decisions = {"r1|1|p1": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"}}
    requests_by_id = {"r1": _request("r1", size="15 oz")}
    catalog_by_key = {(1, "p1"): _row("15.4 oz")}
    violations = find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key)
    assert len(violations) == 1
    assert violations[0]["key"] == "r1|1|p1"
    assert violations[0]["reviewed_by"] == "claude_auto"


def test_does_not_flag_an_exact_match():
    decisions = {"r1|1|p1": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"}}
    requests_by_id = {"r1": _request("r1", size="15 oz")}
    catalog_by_key = {(1, "p1"): _row("15 oz")}
    assert find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key) == []


def test_does_not_flag_a_genuine_cross_unit_conversion():
    decisions = {"r1|1|p1": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"}}
    requests_by_id = {"r1": _request("r1", text="2 L soda", size="2 L")}
    catalog_by_key = {(1, "p1"): _row("67.6 fl oz")}
    assert find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key) == []


def test_does_not_flag_non_acceptable_labels():
    decisions = {"r1|1|p1": {"reviewer_label": "Incorrect", "reviewed_by": "claude_auto"}}
    requests_by_id = {"r1": _request("r1", size="15 oz")}
    catalog_by_key = {(1, "p1"): _row("15.4 oz")}
    assert find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key) == []


def test_does_not_flag_size_any_substitution():
    decisions = {"r1|1|p1": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"}}
    requests_by_id = {"r1": _request("r1", size="15 oz", size_any=True)}
    catalog_by_key = {(1, "p1"): _row("40 oz")}
    assert find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key) == []


def test_missing_request_or_catalog_row_is_skipped_not_crashed():
    decisions = {
        "ghost|1|p1": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"},
        "r1|9|ghost": {"reviewer_label": "Acceptable", "reviewed_by": "claude_auto"},
    }
    requests_by_id = {"r1": _request("r1", size="15 oz")}
    catalog_by_key = {}
    assert find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key) == []
