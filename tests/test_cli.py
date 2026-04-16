"""Tests for the CortexRAG CLI entry points."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag import cli
from cortex_rag.generation import AnswerTimings, ConfluenceAnswerResult, GenerationResult
from cortex_rag.retrieval import SearchResult


def test_similarity_search_cli_formats_results(
    monkeypatch,
    capsys,
) -> None:
    def fake_retrieve_context(query: str, **kwargs: object) -> list[SearchResult]:
        assert query == "How are leads qualified?"
        assert kwargs["candidate_k"] == 10
        assert kwargs["final_k"] == 2
        assert kwargs["min_score"] == 0.7
        return [
            SearchResult(
                chunk_id="overview-3178688:001",
                score=0.9321,
                text="The agent qualifies and prioritizes leads.",
                metadata={"page": "Overview", "section": "Lead qualification"},
            )
        ]

    monkeypatch.setattr(cli, "retrieve_confluence_context", fake_retrieve_context)

    cli.main(["similarity-search", "How are leads qualified?", "--top-k", "2", "--min-score", "0.7"])

    assert capsys.readouterr().out.splitlines() == [
        "1. overview-3178688:001  score=0.9321",
        "   Overview :: Lead qualification",
        "   The agent qualifies and prioritizes leads.",
    ]


def test_similarity_search_cli_skips_empty_metadata_line(
    monkeypatch,
    capsys,
) -> None:
    def fake_retrieve_context(query: str, **kwargs: object) -> list[SearchResult]:
        assert query == "What changed?"
        assert kwargs["candidate_k"] == 10
        assert kwargs["final_k"] == 5
        assert kwargs["min_score"] is None
        return [
            SearchResult(
                chunk_id="overview-3178688:002",
                score=0.5,
                text="First line\nSecond line",
                metadata={},
            )
        ]

    monkeypatch.setattr(cli, "retrieve_confluence_context", fake_retrieve_context)

    cli.main(["similarity-search", "What changed?"])

    assert capsys.readouterr().out.splitlines() == [
        "1. overview-3178688:002  score=0.5000",
        "   First line Second line",
    ]


def test_ask_cli_formats_answer_sources_and_timings(
    monkeypatch,
    capsys,
) -> None:
    def fake_answer_question(question: str, **kwargs: object) -> ConfluenceAnswerResult:
        assert question == "What changed?"
        assert kwargs["top_k"] == 2
        assert kwargs["min_score"] == 0.7
        return ConfluenceAnswerResult(
            question=question,
            answer_mode="normal",
            prompt_path=Path("prompts/confluence_rag.md"),
            backend="chroma",
            collection_name="confluence",
            sources=[
                SearchResult(
                    chunk_id="overview-3178688:001",
                    score=0.9321,
                    text="The agent qualifies and prioritizes leads.",
                    metadata={"page": "Overview", "section": "Lead qualification"},
                )
            ],
            messages=[{"role": "user", "content": "Question:\nWhat changed?"}],
            generation=GenerationResult(
                model="llama3.2:3b",
                content="Grounded answer.",
                first_token_seconds=0.12,
                prompt_eval_count=42,
                eval_count=11,
                done_reason="stop",
            ),
            timings=AnswerTimings(
                embedding_seconds=0.5,
                retrieval_seconds=0.25,
                generation_seconds=1.5,
                total_seconds=2.25,
                first_token_seconds=0.12,
            ),
        )

    monkeypatch.setattr(cli, "answer_confluence_question", fake_answer_question)

    cli.main(["ask", "What changed?", "--top-k", "2", "--min-score", "0.7"])

    assert capsys.readouterr().out.splitlines() == [
        "Answer:",
        "Grounded answer.",
        "",
        "Sources:",
        "1. overview-3178688:001  score=0.9321",
        "   Overview :: Lead qualification",
        "   The agent qualifies and prioritizes leads.",
        "",
        "Timings:",
        "embedding: 0.50s",
        "retrieval: 0.25s",
        "first_token: 0.12s",
        "generation: 1.50s",
        "total: 2.25s",
    ]


def test_ask_cli_skips_generation_output_when_no_context(
    monkeypatch,
    capsys,
) -> None:
    def fake_answer_question(question: str, **kwargs: object) -> ConfluenceAnswerResult:
        return ConfluenceAnswerResult(
            question=question,
            answer_mode="normal",
            prompt_path=Path("prompts/confluence_rag.md"),
            backend="chroma",
            collection_name="confluence",
            sources=[],
            messages=[],
            generation=None,
            timings=AnswerTimings(
                embedding_seconds=0.5,
                retrieval_seconds=0.25,
                generation_seconds=0.0,
                total_seconds=1.25,
                first_token_seconds=None,
            ),
        )

    monkeypatch.setattr(cli, "answer_confluence_question", fake_answer_question)

    cli.main(["ask", "What changed?"])

    assert capsys.readouterr().out.splitlines() == [
        "No relevant context was found. Ollama was not called.",
        "",
        "Timings:",
        "embedding: 0.50s",
        "retrieval: 0.25s",
        "generation: 0.00s",
        "total: 1.25s",
    ]
