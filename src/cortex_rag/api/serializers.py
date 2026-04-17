"""Pure serialization helpers for the thin UI backend."""

from __future__ import annotations

from cortex_rag.api.schemas import (
    AnswerResponse,
    AnswerTimingsPayload,
    GraphEdgePayload,
    GraphNeighborhoodResponse,
    GraphNodePayload,
    SearchResponse,
    SearchResultPayload,
)
from cortex_rag.generation.confluence_answering import ConfluenceAnswerResult
from cortex_rag.graph import GraphNeighborhood
from cortex_rag.retrieval import SearchResult


def build_search_response(query: str, results: list[SearchResult]) -> SearchResponse:
    """Serialize retrieval hits into the `/search` response shape."""

    return SearchResponse(
        query=query,
        result_count=len(results),
        results=[_search_result_payload(result) for result in results],
    )


def build_answer_response(result: ConfluenceAnswerResult) -> AnswerResponse:
    """Serialize a grounded-answer result into the `/answer` response shape."""

    return AnswerResponse(
        question=result.question,
        answer=result.answer,
        answer_mode=result.answer_mode,
        generated=result.generated,
        model=result.model,
        backend=result.backend,
        collection_name=result.collection_name,
        prompt_path=str(result.prompt_path),
        sources=[_search_result_payload(source) for source in result.sources],
        timings=AnswerTimingsPayload(
            embedding_seconds=result.timings.embedding_seconds,
            retrieval_seconds=result.timings.retrieval_seconds,
            generation_seconds=result.timings.generation_seconds,
            total_seconds=result.timings.total_seconds,
            first_token_seconds=result.timings.first_token_seconds,
        ),
    )


def build_graph_neighborhood_response(
    query: str,
    neighborhood: GraphNeighborhood,
) -> GraphNeighborhoodResponse:
    """Serialize a graph neighborhood into the API response shape."""

    highlighted_ids = set(neighborhood.highlighted_node_ids)
    return GraphNeighborhoodResponse(
        query=query,
        result_count=len(neighborhood.seed_node_ids),
        seed_node_ids=list(neighborhood.seed_node_ids),
        nodes=[
            GraphNodePayload(
                id=node.id,
                type=node.type,
                label=node.label,
                highlighted=node.id in highlighted_ids,
                metadata=dict(node.metadata),
            )
            for node in neighborhood.nodes
        ],
        edges=[
            GraphEdgePayload(
                id=edge.id,
                source=edge.source,
                target=edge.target,
                type=edge.type,
                weight=edge.weight,
                metadata=dict(edge.metadata),
            )
            for edge in neighborhood.edges
        ],
    )


def _search_result_payload(result: SearchResult) -> SearchResultPayload:
    return SearchResultPayload(
        chunk_id=result.chunk_id,
        score=result.score,
        text=result.text,
        metadata=dict(result.metadata),
    )
