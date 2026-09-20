"""Checkpoint 4, S1: pin the embedding model and cache the catalog embeddings.

Mirrors retrieval.fit_tfidf's contract rather than inventing a second one: the
embedding matrix is computed once against the frozen catalog and cached to
disk, keyed by everything a stale cache could silently disagree with -- catalog
content, row order, text construction, model identity *and revision*, and the
library versions that produced it. A mismatched key means recompute, never
silent reuse.

The model is pinned by its Hugging Face commit revision, not by tag. Checkpoint
7 requires a pinned model version, and a model re-resolved at run time is not
pinned. MODEL_REVISION is therefore a constant here, not a lookup.

Device is CPU by construction (no device= branch) so reported latency is the
latency a reviewer reproduces on ordinary hardware.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

import retrieval
from retrieval import TEXT_CONSTRUCTION_VERSION, _catalog_text, catalog_hash

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
# Resolved 2026-09-20 from the HF Hub. Pinned deliberately: re-resolving this
# at run time would mean the "pinned model version" Checkpoint 7 asks for is
# whatever upstream happens to be serving that day.
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# Bumped whenever the encode call's own conventions change (normalization,
# truncation, pooling) even if the catalog and the model are identical.
EMBED_CONSTRUCTION_VERSION = "v1"  # L2-normalized, default pooling, max_seq_length 256

OUTPUT_DIR = Path(__file__).resolve().parent / "evaluation_v3"
EMBEDDINGS_PATH = OUTPUT_DIR / "catalog_embeddings.npy"
CACHE_KEY_PATH = OUTPUT_DIR / "catalog_embeddings_key.json"
MANIFEST_PATH = OUTPUT_DIR / "model_manifest.json"

_BATCH_SIZE = 256


def _package_versions() -> dict:
    return {
        pkg: version(pkg)
        for pkg in ("sentence-transformers", "transformers", "torch", "numpy", "pandas")
    }


def cache_key(catalog_df) -> dict:
    """Everything a stale embedding cache could silently disagree with.

    Deliberately parallel to retrieval._cache_key, with the vectorizer
    hyperparameters replaced by the model's identity and revision: a model
    swap, a revision bump, or a change to how the text is built must each
    invalidate the cache on their own, even when the catalog rows are
    byte-identical.
    """
    return {
        "catalog_hash": catalog_hash(catalog_df),
        "row_order": list(zip(catalog_df["store_id"], catalog_df["product_id"].astype(str))),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "text_construction_version": TEXT_CONSTRUCTION_VERSION,
        "embed_construction_version": EMBED_CONSTRUCTION_VERSION,
        "package_versions": _package_versions(),
    }


def _key_fingerprint(key: dict) -> str:
    """A stable hash of the cache key, so the on-disk key file stays small
    (row_order is 31k pairs) while still detecting any change to it."""
    payload = json.dumps(key, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device="cpu")


def embed_catalog(catalog_df, model=None, show_progress: bool = False) -> np.ndarray:
    """Encode every catalog row's text into an L2-normalized embedding matrix.

    Row i of the result corresponds to row i of catalog_df -- the same
    positional contract retrieval._ranked already relies on, which is why
    row_order is part of the cache key.
    """
    model = model or _load_model()
    texts = _catalog_text(catalog_df).tolist()
    matrix = model.encode(
        texts,
        batch_size=_BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=show_progress,
    )
    return np.asarray(matrix, dtype=np.float32)


def load_or_build(catalog_df, embeddings_path: Path = EMBEDDINGS_PATH,
                  key_path: Path = CACHE_KEY_PATH, show_progress: bool = False):
    """Return the cached embedding matrix when its key still matches, else
    recompute and rewrite both files. Never returns a matrix whose key
    disagrees with the current inputs."""
    current = cache_key(catalog_df)
    fingerprint = _key_fingerprint(current)

    if embeddings_path.exists() and key_path.exists():
        with open(key_path) as f:
            cached = json.load(f)
        if cached.get("fingerprint") == fingerprint:
            return np.load(embeddings_path)

    matrix = embed_catalog(catalog_df, show_progress=show_progress)

    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(embeddings_path, matrix)
    with open(key_path, "w") as f:
        json.dump(
            {
                "fingerprint": fingerprint,
                "catalog_hash": current["catalog_hash"],
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "text_construction_version": TEXT_CONSTRUCTION_VERSION,
                "embed_construction_version": EMBED_CONSTRUCTION_VERSION,
                "package_versions": current["package_versions"],
                "n_rows": int(matrix.shape[0]),
                "dimension": int(matrix.shape[1]),
            },
            f,
            indent=2,
        )
        f.write("\n")
    return matrix


def write_manifest(catalog_df, matrix, model, path: Path = MANIFEST_PATH) -> dict:
    manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "dimension": int(matrix.shape[1]),
        "normalization": "L2 (cosine == dot product)",
        "max_seq_length": int(model.max_seq_length),
        "truncation": f"inputs longer than {model.max_seq_length} tokens are truncated",
        "device": "cpu",
        "pooling": "model default (mean pooling)",
        "text_construction_version": TEXT_CONSTRUCTION_VERSION,
        "embed_construction_version": EMBED_CONSTRUCTION_VERSION,
        "catalog_rows": int(matrix.shape[0]),
        "catalog_sha256": catalog_hash(catalog_df),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "package_versions": _package_versions(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest


def main() -> None:
    from run_experiments import _load_catalog

    catalog_df = _load_catalog()
    model = _load_model()

    matrix = embed_catalog(catalog_df, model=model, show_progress=True)
    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_PATH, matrix)

    current = cache_key(catalog_df)
    with open(CACHE_KEY_PATH, "w") as f:
        json.dump(
            {
                "fingerprint": _key_fingerprint(current),
                "catalog_hash": current["catalog_hash"],
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "text_construction_version": TEXT_CONSTRUCTION_VERSION,
                "embed_construction_version": EMBED_CONSTRUCTION_VERSION,
                "package_versions": current["package_versions"],
                "n_rows": int(matrix.shape[0]),
                "dimension": int(matrix.shape[1]),
            },
            f,
            indent=2,
        )
        f.write("\n")

    manifest = write_manifest(catalog_df, matrix, model)

    print(f"catalog rows: {matrix.shape[0]}")
    print(f"embedding dimension: {matrix.shape[1]}")
    print(f"model: {MODEL_ID} @ {MODEL_REVISION[:12]}")
    print(f"wrote {EMBEDDINGS_PATH.name}, {CACHE_KEY_PATH.name}, {MANIFEST_PATH.name}")
    print(f"catalog sha256: {manifest['catalog_sha256'][:16]}...")


if __name__ == "__main__":
    main()
