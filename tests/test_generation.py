"""Tests for Ollama generation helpers."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.generation import (
    AnswerMode,
    GenerationResult,
    build_confluence_rag_messages,
    chat_with_ollama,
    format_retrieval_context,
    normalize_answer_mode,
)
from cortex_rag.retrieval import SearchResult


def test_format_retrieval_context_includes_metadata() -> None:
    results = [
        SearchResult(
            chunk_id="architecture-3309569:001",
            score=0.9123,
            text="The execution layer runs retrieval and generation steps.",
            metadata={"page": "Architecture", "section": "Execution layer"},
        )
    ]

    assert format_retrieval_context(results) == "\n".join(
        [
            "Source 1",
            "Chunk ID: architecture-3309569:001",
            "Page: Architecture",
            "Section: Execution layer",
            "Score: 0.9123",
            "Text:",
            "The execution layer runs retrieval and generation steps.",
        ]
    )


def test_build_confluence_rag_messages_uses_prompt_file(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Answer only from context.", encoding="utf-8")

    messages = build_confluence_rag_messages(
        "What does the execution layer do?",
        [
            SearchResult(
                chunk_id="architecture-3309569:001",
                score=0.8,
                text="The execution layer orchestrates retrieval and generation.",
                metadata={"page": "Architecture", "section": "Execution layer"},
            )
        ],
        prompt_path=prompt_path,
        answer_mode="technical",
    )

    assert messages[0] == {"role": "system", "content": "Answer only from context."}
    assert "Question:\nWhat does the execution layer do?" in messages[1]["content"]
    assert (
        "Answer mode: technical. Use a technical style, emphasizing implementation details, "
        "structure, and precise terminology."
    ) in messages[1]["content"]
    assert "Chunk ID: architecture-3309569:001" in messages[1]["content"]


def test_normalize_answer_mode_accepts_supported_modes() -> None:
    mode: AnswerMode = normalize_answer_mode("Detailed")
    assert mode == "detailed"


def test_normalize_answer_mode_rejects_unknown_modes() -> None:
    try:
        normalize_answer_mode("poetic")
    except ValueError as exc:
        assert "Unsupported answer mode" in str(exc)
    else:
        raise AssertionError("Expected normalize_answer_mode to reject unsupported modes.")


def test_chat_with_ollama_passes_expected_request_options() -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        model = "llama3.2:3b"
        message = type("Message", (), {"content": "Grounded answer."})()
        prompt_eval_count = 42
        eval_count = 11
        done_reason = "stop"

    class FakeClient:
        def __init__(self, *, host: str) -> None:
            captured["host"] = host

        def chat(self, **kwargs: object) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    result = chat_with_ollama(
        [
            {"role": "system", "content": "Answer only from context."},
            {"role": "user", "content": "Question:\nWhat is the architecture?"},
        ],
        host="http://127.0.0.1:11434",
        model="llama3.2:3b",
        temperature=0.1,
        num_ctx=4096,
        keep_alive="10m",
        client_factory=FakeClient,
    )

    assert result == GenerationResult(
        model="llama3.2:3b",
        content="Grounded answer.",
        prompt_eval_count=42,
        eval_count=11,
        done_reason="stop",
    )
    assert captured == {
        "host": "http://127.0.0.1:11434",
        "model": "llama3.2:3b",
        "messages": [
            {"role": "system", "content": "Answer only from context."},
            {"role": "user", "content": "Question:\nWhat is the architecture?"},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
        },
        "keep_alive": "10m",
    }
