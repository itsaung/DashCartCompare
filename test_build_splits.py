"""Tests for build_splits.py: pilot pinning, group-atomic assignment,
determinism, quota-driven allocation, and cross-group overlap detection
(documented, never merged). Small hand-built request lists -- not the real
150-request benchmark, which is exercised by actually running the script."""
import build_splits as bs
from build_benchmark import PILOT_REQUEST_IDS


def _req(rid, group, mode="flexible", answerability="answerable", refs=None):
    return {
        "request_id": rid, "paraphrase_group": group, "matching_mode": mode,
        "answerability": answerability, "reference_product_ids": refs or [],
    }


# --- pilot pinning ----------------------------------------------------------

def test_pilot_group_always_assigned_to_dev(monkeypatch):
    pilot_id = next(iter(PILOT_REQUEST_IDS))
    requests = [_req(pilot_id, "gpilot")] + [_req(f"r{i}", f"g{i}") for i in range(20)]
    assignment = bs.assign_splits(requests)
    assert assignment["group_split"]["gpilot"] == "dev"
    assert assignment["request_split"][pilot_id] == "dev"


def test_pilot_paraphrase_sibling_also_pinned_to_dev(monkeypatch):
    pilot_id = next(iter(PILOT_REQUEST_IDS))
    requests = [_req(pilot_id, "gpilot"), _req("sibling", "gpilot")] + [_req(f"r{i}", f"g{i}") for i in range(20)]
    assignment = bs.assign_splits(requests)
    assert assignment["request_split"]["sibling"] == "dev"


# --- group-atomic assignment -------------------------------------------------

def test_group_members_never_split_across_splits():
    requests = [_req(f"r{i}", "gbig") for i in range(6)] + [_req(f"s{i}", f"g{i}") for i in range(30)]
    assignment = bs.assign_splits(requests)
    group_of_r = {assignment["request_split"][f"r{i}"] for i in range(6)}
    assert len(group_of_r) == 1


def test_check_invariants_passes_on_a_clean_assignment():
    requests = [_req(f"r{i}", f"g{i}") for i in range(30)]
    groups = bs.group_requests(requests)
    assignment = bs.assign_splits(requests)
    assert bs.check_invariants(assignment, groups) == []


# --- determinism --------------------------------------------------------------

def test_assign_splits_is_deterministic_across_calls():
    requests = [_req(f"r{i}", f"g{i}", mode="exact" if i % 2 else "flexible") for i in range(40)]
    a1 = bs.assign_splits(requests)
    a2 = bs.assign_splits(requests)
    assert a1["request_split"] == a2["request_split"]
    assert a1["group_split"] == a2["group_split"]


def test_assign_splits_ignores_input_list_order():
    requests = [_req(f"r{i}", f"g{i}") for i in range(30)]
    a1 = bs.assign_splits(requests)
    a2 = bs.assign_splits(list(reversed(requests)))
    assert a1["request_split"] == a2["request_split"]


# --- quota-driven allocation --------------------------------------------------

def test_counts_sum_to_total_requests():
    requests = [_req(f"r{i}", f"g{i}") for i in range(50)]
    assignment = bs.assign_splits(requests)
    assert sum(assignment["counts"].values()) == 50


def test_no_pilot_requests_roughly_matches_target_ratios():
    requests = [_req(f"r{i}", f"g{i}") for i in range(100)]  # single-member groups, no pilot overlap
    assignment = bs.assign_splits(requests)
    # target is 60/20/20 of 100 = 60/20/20 exactly, with single-request groups
    # the greedy should hit it exactly (no group-size remainder to absorb)
    assert assignment["counts"] == assignment["target"]


# --- cross-group overlap: documented, never merged ---------------------------

def test_identical_reference_sets_across_groups_are_reported_not_merged():
    requests = [
        _req("r1", "gA", mode="exact", refs=[[1, "p1"]]),
        _req("r2", "gB", mode="flexible", refs=[[1, "p1"]]),
    ]
    groups = bs.group_requests(requests)
    overlaps = bs.audit_cross_group_overlaps(groups)
    assert len(overlaps) == 1
    assert overlaps[0]["groups"] == ["gA", "gB"]
    assert overlaps[0]["request_ids"] == ["r1", "r2"]
    # still two distinct groups in the group map -- overlap detection must
    # not itself merge/mutate anything
    assert set(groups.keys()) == {"gA", "gB"}


def test_disjoint_reference_sets_are_not_reported_as_overlapping():
    requests = [
        _req("r1", "gA", refs=[[1, "p1"]]),
        _req("r2", "gB", refs=[[1, "p2"]]),
    ]
    groups = bs.group_requests(requests)
    assert bs.audit_cross_group_overlaps(groups) == []


def test_empty_reference_sets_are_never_reported_as_overlapping():
    requests = [_req("r1", "gA", refs=[]), _req("r2", "gB", refs=[])]
    groups = bs.group_requests(requests)
    assert bs.audit_cross_group_overlaps(groups) == []
