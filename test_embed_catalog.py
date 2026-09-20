"""Tests for embed_catalog.py: cache-key sensitivity and the embedding
contract. Small hand-built fixtures, not the real 31k-row catalog.

The model itself is not loaded here -- a fake encoder stands in, because what
these tests check is the cache/key/manifest logic around the model, not
sentence-transformers' own behavior. The one thing that genuinely needs the
real model (that it loads at the pinned revision and returns 384 normalized
dimensions) is asserted in a separate test marked `model`, skipped when the
weights aren't available offline.
"""
import json

import numpy as np
import pandas as pd
import pytest

import embed_catalog
from embed_catalog import _key_fingerprint, cache_key, embed_catalog as encode_catalog, load_or_build


def _catalog(rows=None):
    rows = rows or [
        {"store_id": "s1", "product_id": "p1", "raw_title": "Whole Milk 1 gal",
         "brand": None, "variant": None},
        {"store_id": "s1", "product_id": "p2", "raw_title": "Oat Milk 64 fl oz",
         "brand": None, "variant": None},
    ]
    return pd.DataFrame(rows)


class _FakeModel:
    """Deterministic stand-in: embeds each text as a normalized vector whose
    entries depend only on the text, so identical input gives identical
    output and different input gives different output."""

    max_seq_length = 256

    def __init__(self, dim=4):
        self.dim = dim
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        out = []
        for t in texts:
            v = np.array([(hash((t, i)) % 1000) + 1 for i in range(self.dim)], dtype=np.float32)
            out.append(v / np.linalg.norm(v))
        return np.vstack(out)


# --- embedding contract -----------------------------------------------------

def test_embed_returns_one_normalized_row_per_catalog_row():
    df = _catalog()
    m = encode_catalog(df, model=_FakeModel())
    assert m.shape == (2, 4)
    # L2-normalized, so cosine is a plain dot product downstream.
    np.testing.assert_allclose(np.linalg.norm(m, axis=1), [1.0, 1.0], rtol=1e-6)


def test_embed_row_order_follows_catalog_order():
    df = _catalog()
    m1 = encode_catalog(df, model=_FakeModel())
    # Same rows, reversed: row 0's embedding must now be what was row 1's.
    m2 = encode_catalog(df.iloc[::-1].reset_index(drop=True), model=_FakeModel())
    np.testing.assert_allclose(m1[0], m2[1], rtol=1e-6)
    np.testing.assert_allclose(m1[1], m2[0], rtol=1e-6)


def test_embed_is_float32():
    m = encode_catalog(_catalog(), model=_FakeModel())
    assert m.dtype == np.float32


# --- cache key sensitivity --------------------------------------------------

def test_cache_key_stable_for_identical_catalog():
    assert _key_fingerprint(cache_key(_catalog())) == _key_fingerprint(cache_key(_catalog()))


def test_cache_key_changes_when_catalog_content_changes():
    other = _catalog([
        {"store_id": "s1", "product_id": "p1", "raw_title": "Whole Milk 2 gal",
         "brand": None, "variant": None},
        {"store_id": "s1", "product_id": "p2", "raw_title": "Oat Milk 64 fl oz",
         "brand": None, "variant": None},
    ])
    assert _key_fingerprint(cache_key(_catalog())) != _key_fingerprint(cache_key(other))


def test_cache_key_changes_when_row_order_changes():
    df = _catalog()
    reordered = df.iloc[::-1].reset_index(drop=True)
    assert _key_fingerprint(cache_key(df)) != _key_fingerprint(cache_key(reordered))


def test_cache_key_changes_when_model_revision_changes(monkeypatch):
    df = _catalog()
    before = _key_fingerprint(cache_key(df))
    monkeypatch.setattr(embed_catalog, "MODEL_REVISION", "0" * 40)
    assert _key_fingerprint(cache_key(df)) != before


def test_cache_key_changes_when_model_id_changes(monkeypatch):
    df = _catalog()
    before = _key_fingerprint(cache_key(df))
    monkeypatch.setattr(embed_catalog, "MODEL_ID", "some-other/model")
    assert _key_fingerprint(cache_key(df)) != before


def test_cache_key_changes_when_embed_construction_version_changes(monkeypatch):
    df = _catalog()
    before = _key_fingerprint(cache_key(df))
    monkeypatch.setattr(embed_catalog, "EMBED_CONSTRUCTION_VERSION", "v2")
    assert _key_fingerprint(cache_key(df)) != before


def test_cache_key_changes_when_a_package_version_changes(monkeypatch):
    df = _catalog()
    before = _key_fingerprint(cache_key(df))
    monkeypatch.setattr(embed_catalog, "_package_versions", lambda: {"torch": "0.0.0"})
    assert _key_fingerprint(cache_key(df)) != before


# --- load_or_build ----------------------------------------------------------

def test_load_or_build_reuses_cache_when_key_matches(tmp_path, monkeypatch):
    df = _catalog()
    fake = _FakeModel()
    monkeypatch.setattr(embed_catalog, "_load_model", lambda: fake)
    emb, key = tmp_path / "e.npy", tmp_path / "k.json"

    first = load_or_build(df, embeddings_path=emb, key_path=key)
    second = load_or_build(df, embeddings_path=emb, key_path=key)

    assert fake.calls == 1, "second call should have hit the cache, not re-encoded"
    np.testing.assert_allclose(first, second)


def test_load_or_build_recomputes_when_key_is_stale(tmp_path, monkeypatch):
    df = _catalog()
    fake = _FakeModel()
    monkeypatch.setattr(embed_catalog, "_load_model", lambda: fake)
    emb, key = tmp_path / "e.npy", tmp_path / "k.json"

    load_or_build(df, embeddings_path=emb, key_path=key)
    monkeypatch.setattr(embed_catalog, "MODEL_REVISION", "0" * 40)
    load_or_build(df, embeddings_path=emb, key_path=key)

    assert fake.calls == 2, "a revision bump must invalidate the cache on its own"


def test_load_or_build_writes_key_file_with_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(embed_catalog, "_load_model", lambda: _FakeModel())
    emb, key = tmp_path / "e.npy", tmp_path / "k.json"
    load_or_build(_catalog(), embeddings_path=emb, key_path=key)

    written = json.loads(key.read_text())
    assert written["n_rows"] == 2
    assert written["dimension"] == 4
    assert written["model_revision"] == embed_catalog.MODEL_REVISION


def test_load_or_build_recomputes_when_embeddings_file_missing(tmp_path, monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(embed_catalog, "_load_model", lambda: fake)
    emb, key = tmp_path / "e.npy", tmp_path / "k.json"

    load_or_build(_catalog(), embeddings_path=emb, key_path=key)
    emb.unlink()
    load_or_build(_catalog(), embeddings_path=emb, key_path=key)

    assert fake.calls == 2


# --- manifest ---------------------------------------------------------------

def test_write_manifest_records_pinned_revision_and_catalog_hash(tmp_path):
    df = _catalog()
    matrix = encode_catalog(df, model=_FakeModel())
    path = tmp_path / "manifest.json"
    manifest = embed_catalog.write_manifest(df, matrix, _FakeModel(), path=path)

    assert manifest["model_revision"] == embed_catalog.MODEL_REVISION
    assert manifest["catalog_rows"] == 2
    assert manifest["device"] == "cpu"
    assert manifest["catalog_sha256"] == embed_catalog.catalog_hash(df)
    assert json.loads(path.read_text())["model_id"] == embed_catalog.MODEL_ID


# --- the real model ---------------------------------------------------------

@pytest.mark.model
def test_real_model_loads_at_pinned_revision_and_returns_384_normalized_dims():
    """Skipped when the pinned weights aren't available offline -- the rest of
    the suite must stay runnable without a model download."""
    try:
        model = embed_catalog._load_model()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"pinned model unavailable: {exc}")

    m = encode_catalog(_catalog(), model=model)
    assert m.shape == (2, 384)
    np.testing.assert_allclose(np.linalg.norm(m, axis=1), [1.0, 1.0], rtol=1e-5)
