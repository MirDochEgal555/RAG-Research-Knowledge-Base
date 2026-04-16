"""Shared embedding model helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
    return SentenceTransformer(model_name, **kwargs)


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
