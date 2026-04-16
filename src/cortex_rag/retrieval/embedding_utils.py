"""Shared embedding model helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import os
from pathlib import Path
from typing import Any, Protocol


class TextEncoder(Protocol):
    """Minimal protocol for sentence embedding backends."""

    def encode(self, texts: Sequence[str], **kwargs: object) -> Any:
        """Return one vector per input text."""


def load_sentence_transformer(*, model_name: str, device: str | None) -> TextEncoder:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required to generate embeddings and query the vector store. "
            "Install project dependencies before running this step."
        ) from exc

    kwargs: dict[str, object] = {}
    if device:
        kwargs["device"] = device
    if _cached_hugging_face_model_dir(model_name) is not None:
        kwargs["local_files_only"] = True
    try:
        return SentenceTransformer(model_name, **kwargs)
    except Exception:
        # When the model is already cached locally, a local-files-only retry keeps
        # query-time embedding generation working even if network access is blocked.
        offline_kwargs = dict(kwargs)
        offline_kwargs["local_files_only"] = True
        try:
            return SentenceTransformer(model_name, **offline_kwargs)
        except Exception as exc:
            raise RuntimeError(
                "Unable to load the embedding model. "
                "Ensure the model is cached locally or pass a local model path."
            ) from exc


def _cached_hugging_face_model_dir(model_name: str) -> Path | None:
    model_path = Path(model_name)
    if model_path.exists():
        return model_path
    if "/" not in model_name:
        return None

    hf_home = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
    cached_dir = hf_home / "hub" / f"models--{model_name.replace('/', '--')}"
    return cached_dir if cached_dir.exists() else None


def encode_texts(
    encoder: TextEncoder,
    texts: Sequence[str],
    *,
    batch_size: int,
    normalize_embeddings: bool,
) -> list[list[float]]:
    if not texts:
        return []

    try:
        encoded = encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=normalize_embeddings,
        )
    except TypeError:
        encoded = encoder.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
        )

    vectors = [vector_to_list(vector) for vector in encoded]
    if len(vectors) != len(texts):
        raise ValueError("Encoder returned a different number of vectors than input texts.")
    return vectors


def vector_to_list(vector: object) -> list[float]:
    if hasattr(vector, "tolist"):
        values = vector.tolist()
    else:
        values = vector

    if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
        raise TypeError("Embedding vector is not iterable.")

    return [float(value) for value in values]
