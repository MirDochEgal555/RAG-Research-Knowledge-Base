"""Tests for sentence-transformer loading helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.retrieval import embedding_utils


def test_load_sentence_transformer_retries_from_local_cache(monkeypatch) -> None:
    embedding_utils.clear_sentence_transformer_cache()
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("HF_HOME", str(Path.cwd() / "scratch_pytest" / "hf-empty-cache"))

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            calls.append({"model_name": model_name, **kwargs})
            if not kwargs.get("local_files_only"):
                raise RuntimeError("network unavailable")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    model = embedding_utils.load_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
    )

    assert isinstance(model, FakeSentenceTransformer)
    assert calls == [
        {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "device": "cpu",
        },
        {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "device": "cpu",
            "local_files_only": True,
        },
    ]


def test_load_sentence_transformer_prefers_existing_cache_dir(monkeypatch, tmp_path: Path) -> None:
    embedding_utils.clear_sentence_transformer_cache()
    calls: list[dict[str, object]] = []
    cache_root = tmp_path / "huggingface" / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
    cache_root.mkdir(parents=True)

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            calls.append({"model_name": model_name, **kwargs})

    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    model = embedding_utils.load_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device=None,
    )

    assert isinstance(model, FakeSentenceTransformer)
    assert calls == [
        {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "local_files_only": True,
        }
    ]


def test_load_sentence_transformer_reuses_cached_encoder(monkeypatch) -> None:
    embedding_utils.clear_sentence_transformer_cache()
    calls: list[dict[str, object]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            calls.append({"model_name": model_name, **kwargs})

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setenv("HF_HOME", str(Path.cwd() / "scratch_pytest" / "hf-empty-cache"))

    first = embedding_utils.load_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
    )
    second = embedding_utils.load_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
    )

    assert first is second
    assert len(calls) == 1


def test_preload_sentence_transformer_populates_cache(monkeypatch) -> None:
    embedding_utils.clear_sentence_transformer_cache()
    calls: list[dict[str, object]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            calls.append({"model_name": model_name, **kwargs})

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setenv("HF_HOME", str(Path.cwd() / "scratch_pytest" / "hf-empty-cache"))

    preloaded = embedding_utils.preload_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device=None,
    )
    loaded = embedding_utils.load_sentence_transformer(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        device=None,
    )

    assert preloaded is loaded
    assert len(calls) == 1
