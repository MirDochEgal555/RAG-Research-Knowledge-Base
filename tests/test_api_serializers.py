"""Tests for API serialization helpers."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.api.serializers import (
    build_answer_response,
    build_graph_neighborhood_response,
    build_search_response,
)
from cortex_rag.generation import AnswerTimings, ConfluenceAnswerResult, GenerationResult
from cortex_rag.graph import GraphEdge, GraphNeighborhood, GraphNode
from cortex_rag.retrieval import SearchResult


def test_build_search_response_serializes_results() -> None:
    response = build_search_response(
        "What changed?",
        [
            SearchResult(
                chunk_id="overview-3178688:001",
                score=0.9321,
                text="The agent qualifies and prioritizes leads.",
                metadata={"page": "Overview", "section": "Lead qualification"},
            )
        ],
    )

    assert response.query == "What changed?"
    assert response.result_count == 1
    assert response.results[0].chunk_id == "overview-3178688:001"
    assert response.results[0].metadata["page"] == "Overview"


def test_build_answer_response_serializes_structured_answer() -> None:
    result = ConfluenceAnswerResult(
        question="What changed?",
        answer_mode="technical",
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
            first_token_seconds=0.14,
            prompt_eval_count=42,
            eval_count=11,
            done_reason="stop",
        ),
        timings=AnswerTimings(
            embedding_seconds=0.5,
            retrieval_seconds=0.25,
            generation_seconds=1.0,
            total_seconds=1.75,
            first_token_seconds=0.14,
        ),
    )

    response = build_answer_response(result)

    assert response.question == "What changed?"
    assert response.answer == "Grounded answer."
    assert response.generated is True
    assert response.backend == "chroma"
    assert response.timings.first_token_seconds == 0.14
    assert response.sources[0].chunk_id == "overview-3178688:001"


def test_build_graph_neighborhood_response_creates_document_and_chunk_nodes() -> None:
    response = build_graph_neighborhood_response(
        "What changed?",
        GraphNeighborhood(
            seed_node_ids=["chunk::architecture-3309569:001", "chunk::architecture-3309569:002"],
            highlighted_node_ids=["chunk::architecture-3309569:001", "document::ASA/architecture-3309569.md"],
            nodes=[
                GraphNode(
                    id="document::ASA/architecture-3309569.md",
                    type="document",
                    label="Architecture",
                    metadata={"page": "Architecture"},
                ),
                GraphNode(
                    id="chunk::architecture-3309569:001",
                    type="chunk",
                    label="Execution layer",
                    metadata={"chunk_id": "architecture-3309569:001"},
                ),
                GraphNode(
                    id="chunk::architecture-3309569:002",
                    type="chunk",
                    label="Orchestration",
                    metadata={"chunk_id": "architecture-3309569:002"},
                ),
            ],
            edges=[
                GraphEdge(
                    id="document::ASA/architecture-3309569.md--chunk::architecture-3309569:001::belongs_to",
                    source="document::ASA/architecture-3309569.md",
                    target="chunk::architecture-3309569:001",
                    type="belongs_to",
                    weight=1.0,
                    metadata={"reason": "chunk_source_membership"},
                ),
                GraphEdge(
                    id="document::ASA/architecture-3309569.md--chunk::architecture-3309569:002::belongs_to",
                    source="document::ASA/architecture-3309569.md",
                    target="chunk::architecture-3309569:002",
                    type="belongs_to",
                    weight=1.0,
                    metadata={"reason": "chunk_source_membership"},
                ),
                GraphEdge(
                    id="chunk::architecture-3309569:001--chunk::architecture-3309569:002::similar_to",
                    source="chunk::architecture-3309569:001",
                    target="chunk::architecture-3309569:002",
                    type="similar_to",
                    weight=0.88,
                    metadata={"reason": "embedding_similarity"},
                ),
            ],
        ),
    )

    assert response.query == "What changed?"
    assert response.result_count == 2
    assert response.seed_node_ids == [
        "chunk::architecture-3309569:001",
        "chunk::architecture-3309569:002",
    ]
    assert {node.id for node in response.nodes} == {
        "document::ASA/architecture-3309569.md",
        "chunk::architecture-3309569:001",
        "chunk::architecture-3309569:002",
    }
    assert [edge.type for edge in response.edges] == ["belongs_to", "belongs_to", "similar_to"]
    assert response.edges[2].metadata["reason"] == "embedding_similarity"
    assert response.nodes[0].highlighted is True
