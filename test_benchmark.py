"""Tests for build_benchmark.py's validation and export logic. Fixtures are
small hand-built catalogs/pools/decisions, not the real 31k-row frozen
catalog -- the real catalog is exercised by actually running the script
(see the README-style note in build_benchmark.py's docstring), not by these
unit tests."""
import pandas as pd
import pytest

import build_benchmark as bb


def _catalog(rows=None):
    rows = rows if rows is not None else [
        {"store_id": 1, "product_id": "p1"},
        {"store_id": 1, "product_id": "p2"},
    ]
    return pd.DataFrame(rows)


def _request(request_id="r001", group="g1", answerability="answerable"):
    return {
        "request_id": request_id, "text": "milk", "paraphrase_group": group,
        "matching_mode": "flexible", "answerability": answerability,
        "expected": {"brand": None, "variant": None, "size": None, "quantity": 1,
                     "allowed_substitutions": {}},
        "reference_product_ids": [[1, "p1"]], "hard_negative_product_ids": [],
    }


def _decision(request_id, store_id, product_id, label="Acceptable", **overrides):
    d = {
        "reviewer_label": label,
        "catalog_version_sha256": "CATSHA",
        "request_version": bb.REQUEST_VERSION,
        "labeling_guideline_version": bb.LABELING_GUIDELINE_VERSION,
        "request_content_sha256": None,  # filled by caller from real hash when needed
        "is_best_guess": False,
    }
    d.update(overrides)
    return d


def _manifest(catalog_sha="CATSHA", decisions_sha="DECSHA"):
    return {"catalog_version": {"sha256": catalog_sha}, "current_decisions_sha256": decisions_sha}


def _pool(request_id="r001", pairs=(("1", "p1"),)):
    return [{"request_id": request_id,
             "candidates": [{"store_id": int(s), "product_id": pid} for s, pid in pairs]}]


@pytest.fixture(autouse=True)
def _fixed_manifest_hashes(monkeypatch, tmp_path):
    """Point the module's hash-of-file helpers at values matching _manifest()
    without touching the real benchmark_catalog_frozen.csv / decisions file."""
    monkeypatch.setattr(bb, "_sha256_bytes", lambda path: "CATSHA" if "catalog" in path.name else "DECSHA")


@pytest.fixture(autouse=True)
def _single_pilot_request(monkeypatch):
    """Shrink PILOT_REQUEST_IDS so tests don't need to satisfy the real
    46-request pilot membership check."""
    monkeypatch.setattr(bb, "PILOT_REQUEST_IDS", frozenset(["r001"]))


def _reqs(*requests):
    return requests


# --- manifest hash checks --------------------------------------------------

def test_manifest_hash_mismatch_fails_validation(monkeypatch):
    monkeypatch.setattr(bb, "REQUESTS", _reqs(_request()))
    reqs = [_request()]
    monkeypatch.setattr(bb, "REQUESTS", reqs)
    req_hash = bb._sha256_json(reqs[0])
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", request_content_sha256=req_hash)}
    pool = _pool()
    report = bb.validate(_catalog(), pool, decisions, _manifest(catalog_sha="WRONG"))
    assert not report["pass"]
    assert "manifest_catalog_hash_matches_file" in report["errors"]


# --- duplicate identity / request id checks --------------------------------

def test_duplicate_catalog_identity_fails():
    dup_catalog = _catalog([{"store_id": 1, "product_id": "p1"}, {"store_id": 1, "product_id": "p1"}])
    report = bb.validate(dup_catalog, [], {}, _manifest())
    assert "no_duplicate_catalog_identities" in report["errors"]


def test_duplicate_request_ids_fails(monkeypatch):
    monkeypatch.setattr(bb, "REQUESTS", _reqs(_request(), _request()))
    report = bb.validate(_catalog(), [], {}, _manifest())
    assert "no_duplicate_request_ids" in report["errors"]


# --- per-pair checks --------------------------------------------------------

def test_missing_product_in_catalog_fails(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    pool = _pool(pairs=(("9", "ghost"),))  # store 9 / ghost not in catalog
    decisions = {"r001|9|ghost": _decision("r001", 9, "ghost", request_content_sha256=req_hash)}
    report = bb.validate(_catalog(), pool, decisions, _manifest())
    assert "every_pair_product_in_catalog" in report["errors"]


def test_missing_decision_for_pool_pair_fails(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    report = bb.validate(_catalog(), _pool(), {}, _manifest())
    assert "every_pair_has_a_decision" in report["errors"]


def test_invalid_label_fails(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", label="Maybe", request_content_sha256=req_hash)}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert "all_reviewer_labels_valid" in report["errors"]


def test_stale_request_content_hash_fails(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", request_content_sha256="stale-hash")}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert "no_version_or_hash_mismatches" in report["errors"]


def test_best_guess_without_conservative_label_fails(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", request_content_sha256=req_hash, is_best_guess=True)}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert "guessed_labels_carry_conservative_interpretation" in report["errors"]


def test_best_guess_with_conservative_label_passes_that_check(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    decisions = {"r001|1|p1": _decision(
        "r001", 1, "p1", request_content_sha256=req_hash, is_best_guess=True, conservative_label="Needs clarification",
    )}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert "guessed_labels_carry_conservative_interpretation" not in report["errors"]


def test_a_fully_clean_fixture_passes(monkeypatch):
    req = _request()
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", request_content_sha256=req_hash)}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert report["pass"], report["errors"]


# --- paraphrase-group conflicts ---------------------------------------------

def test_conflicting_labels_within_paraphrase_group_fails(monkeypatch):
    r1 = _request("r001", group="g1")
    r2 = _request("r002", group="g1")
    monkeypatch.setattr(bb, "REQUESTS", _reqs(r1, r2))
    h1, h2 = bb._sha256_json(r1), bb._sha256_json(r2)
    pool = [
        {"request_id": "r001", "candidates": [{"store_id": 1, "product_id": "p1"}]},
        {"request_id": "r002", "candidates": [{"store_id": 1, "product_id": "p1"}]},
    ]
    decisions = {
        "r001|1|p1": _decision("r001", 1, "p1", label="Acceptable", request_content_sha256=h1),
        "r002|1|p1": _decision("r002", 1, "p1", label="Incorrect", request_content_sha256=h2),
    }
    report = bb.validate(_catalog(), pool, decisions, _manifest())
    assert "no_paraphrase_group_label_conflicts" in report["errors"]


def test_agreeing_labels_within_paraphrase_group_passes(monkeypatch):
    r1 = _request("r001", group="g1")
    r2 = _request("r002", group="g1")
    monkeypatch.setattr(bb, "REQUESTS", _reqs(r1, r2))
    h1, h2 = bb._sha256_json(r1), bb._sha256_json(r2)
    pool = [
        {"request_id": "r001", "candidates": [{"store_id": 1, "product_id": "p1"}]},
        {"request_id": "r002", "candidates": [{"store_id": 1, "product_id": "p1"}]},
    ]
    decisions = {
        "r001|1|p1": _decision("r001", 1, "p1", label="Acceptable", request_content_sha256=h1),
        "r002|1|p1": _decision("r002", 1, "p1", label="Acceptable", request_content_sha256=h2),
    }
    report = bb.validate(_catalog(), pool, decisions, _manifest())
    assert "no_paraphrase_group_label_conflicts" not in report["errors"]


# --- request-level answerability audit (info, not fatal) -------------------

def test_answerable_request_with_no_acceptable_candidate_is_flagged_not_failed(monkeypatch):
    req = _request(answerability="answerable")
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    req_hash = bb._sha256_json(req)
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", label="Incorrect", request_content_sha256=req_hash)}
    report = bb.validate(_catalog(), _pool(), decisions, _manifest())
    assert report["checks"]["answerable_requests_with_no_known_positive_in_pool"]["count"] == 1
    assert "answerable_requests_with_no_known_positive_in_pool" in report["warnings"]
    # this is a warning, not a validation error on its own
    assert "answerable_requests_with_no_known_positive_in_pool" not in report["errors"]


def test_no_match_request_missing_from_audit_table_fails(monkeypatch):
    req = _request(request_id="r999", answerability="no_acceptable_match")
    req = {**req, "reference_product_ids": []}
    monkeypatch.setattr(bb, "REQUESTS", _reqs(req))
    monkeypatch.setattr(bb, "NO_MATCH_AUDIT", {})
    report = bb.validate(_catalog(), [], {}, _manifest())
    assert "every_no_match_request_has_an_audit_entry" in report["errors"]
    assert "r999" in report["checks"]["every_no_match_request_has_an_audit_entry"]["examples"]


# --- exports -----------------------------------------------------------------

def test_export_pairs_uses_conservative_label_fallback():
    pool = _pool()
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", label="Acceptable")}
    rows = bb.export_pairs(pool, decisions)
    assert rows[0]["conservative_label"] == "Acceptable"  # falls back to reviewer_label


def test_export_pairs_preserves_explicit_conservative_label():
    pool = _pool()
    decisions = {"r001|1|p1": _decision("r001", 1, "p1", label="Acceptable", conservative_label="Needs clarification")}
    rows = bb.export_pairs(pool, decisions)
    assert rows[0]["conservative_label"] == "Needs clarification"


def test_export_requests_flags_pilot_membership(monkeypatch):
    monkeypatch.setattr(bb, "PILOT_REQUEST_IDS", frozenset(["r001"]))
    monkeypatch.setattr(bb, "REQUESTS", _reqs(_request("r001"), _request("r002")))
    out = bb.export_requests()
    flags = {r["request_id"]: r["is_pilot"] for r in out}
    assert flags == {"r001": True, "r002": False}
