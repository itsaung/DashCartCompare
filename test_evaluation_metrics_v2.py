"""Tests for evaluation_metrics_v2.py's own new logic: the three-source
merged label lookup (v1 pool pairs + v1 additional judgments + v2's own
additional judgments)."""
import json

import evaluation_metrics_v2 as em2


def test_merged_lookup_combines_all_three_sources_without_overriding_earlier_ones(tmp_path, monkeypatch):
    v1_dir = tmp_path / "evaluation"
    v1_dir.mkdir()
    v2_dir = tmp_path / "evaluation_v2"
    v2_dir.mkdir()

    (v1_dir / "benchmark_pairs.jsonl").write_text(
        '{"request_id": "r1", "store_id": 1, "product_id": "p1", '
        '"reviewer_label": "Acceptable", "conservative_label": "Acceptable", "is_best_guess": false}\n'
    )
    (v1_dir / "additional_judgments.json").write_text(json.dumps({
        "r2|1|p2": {"request_id": "r2", "store_id": 1, "product_id": "p2",
                    "reviewer_label": "Incorrect", "conservative_label": "Incorrect", "is_best_guess": False},
    }))
    (v2_dir / "additional_judgments.json").write_text(json.dumps({
        "r3|1|p3": {"request_id": "r3", "store_id": 1, "product_id": "p3",
                    "reviewer_label": "Acceptable", "conservative_label": "Acceptable", "is_best_guess": False},
        # r1|1|p1 also appears here (as if the size baseline re-surfaced it) --
        # v1's own pool label must win, never be overridden by this file.
        "r1|1|p1": {"request_id": "r1", "store_id": 1, "product_id": "p1",
                    "reviewer_label": "Incorrect", "conservative_label": "Incorrect", "is_best_guess": False},
    }))

    monkeypatch.setattr(em2, "V1_DIR", v1_dir)
    monkeypatch.setattr(em2, "OUT_DIR", v2_dir)

    lookup = em2.load_merged_label_lookup()
    assert lookup[("r1", 1, "p1")]["practical"] == "Acceptable"  # v1 pool wins
    assert lookup[("r2", 1, "p2")]["practical"] == "Incorrect"   # from v1 additional
    assert lookup[("r3", 1, "p3")]["practical"] == "Acceptable"  # from v2 additional


def test_merged_lookup_without_a_v2_additional_judgments_file_still_works(tmp_path, monkeypatch):
    v1_dir = tmp_path / "evaluation"
    v1_dir.mkdir()
    v2_dir = tmp_path / "evaluation_v2"
    v2_dir.mkdir()
    (v1_dir / "benchmark_pairs.jsonl").write_text(
        '{"request_id": "r1", "store_id": 1, "product_id": "p1", '
        '"reviewer_label": "Acceptable", "conservative_label": "Acceptable", "is_best_guess": false}\n'
    )
    (v1_dir / "additional_judgments.json").write_text("{}")

    monkeypatch.setattr(em2, "V1_DIR", v1_dir)
    monkeypatch.setattr(em2, "OUT_DIR", v2_dir)

    lookup = em2.load_merged_label_lookup()
    assert lookup[("r1", 1, "p1")]["practical"] == "Acceptable"
