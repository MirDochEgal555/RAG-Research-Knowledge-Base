"""Retrieve Confluence context and answer the question with Ollama."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.config import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_NUM_CTX,
    DEFAULT_OLLAMA_NUM_PREDICT,
    DEFAULT_OLLAMA_TEMPERATURE,
    DEFAULT_RAG_ANSWER_MODE,
    DEFAULT_RAG_PROMPT_PATH,
    DEFAULT_VECTOR_COLLECTION,
    VECTOR_DB_DIR,
)
from cortex_rag.generation import GenerationResult, build_confluence_rag_messages, chat_with_ollama
from cortex_rag.retrieval import (
    SearchResult,
    embed_confluence_query,
    retrieve_confluence_context_by_embedding,
)


def main() -> None:
    _configure_console_output()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Question to answer from the Confluence vector store.")
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=10,
        help="Number of raw retrieval candidates before reranking.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=2,
        help="Number of reranked chunks to include in the prompt.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Optional minimum similarity score required for a chunk to be used.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "chroma", "faiss"),
        default="auto",
        help="Vector store backend. Defaults to the manifest backend when available.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_VECTOR_COLLECTION,
        help="Collection name to query.",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=VECTOR_DB_DIR,
        help="Directory where the vector store files are persisted.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Optional SentenceTransformer model name or local path override for query embedding.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Optional SentenceTransformer device override, for example cpu or cuda.",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_RAG_PROMPT_PATH,
        help="Prompt template file used as the system message.",
    )
    parser.add_argument(
        "--mode",
        choices=("concise", "normal", "detailed", "bullet_summary", "technical"),
        default=DEFAULT_RAG_ANSWER_MODE,
        help="Answer style injected into the prompt.",
    )
    parser.add_argument(
        "--ollama-host",
        default=DEFAULT_OLLAMA_HOST,
        help="Ollama host URL.",
    )
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Ollama model name to use for answer generation.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_OLLAMA_TEMPERATURE,
        help="Generation temperature passed to Ollama.",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=min(DEFAULT_OLLAMA_NUM_CTX, 4096),
        help="Context window passed to Ollama.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_OLLAMA_NUM_PREDICT,
        help="Maximum number of tokens Ollama should generate.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream the answer as tokens arrive and report time to first token.",
    )
    args = parser.parse_args()

    total_started_at = perf_counter()

    embedding_started_at = perf_counter()
    query_embedding, manifest = embed_confluence_query(
        args.query,
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        backend=args.backend,
        model_name=args.embedding_model,
        device=args.device,
    )
    embedding_seconds = perf_counter() - embedding_started_at

    retrieval_started_at = perf_counter()
    results = retrieve_confluence_context_by_embedding(
        args.query,
        query_embedding,
        candidate_k=args.candidate_k,
        final_k=args.top_k,
        min_score=args.min_score,
        persist_dir=args.persist_dir,
        collection_name=manifest.collection_name,
        backend=manifest.backend,
    )
    retrieval_seconds = perf_counter() - retrieval_started_at

    if not results:
        print("No relevant context was found. Ollama was not called.")
        print()
        _print_timings(
            embedding_seconds=embedding_seconds,
            retrieval_seconds=retrieval_seconds,
            generation_seconds=0.0,
            total_seconds=perf_counter() - total_started_at,
        )
        return

    messages = build_confluence_rag_messages(
        args.query,
        results,
        prompt_path=args.prompt,
        answer_mode=args.mode,
    )
    generation_started_at = perf_counter()
    answer = _generate_answer(args, messages)
    generation_seconds = perf_counter() - generation_started_at
    total_seconds = perf_counter() - total_started_at

    if not args.stream:
        print("Answer:")
        print(answer.content)
        print()
    else:
        print()
        print()
    print("Sources:")
    _print_search_results(results)
    print()
    _print_timings(
        embedding_seconds=embedding_seconds,
        retrieval_seconds=retrieval_seconds,
        generation_seconds=generation_seconds,
        total_seconds=total_seconds,
        first_token_seconds=answer.first_token_seconds,
    )


def _configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _print_search_results(results: list[SearchResult]) -> None:
    for index, result in enumerate(results, start=1):
        page = result.metadata.get("page", "")
        section = result.metadata.get("section", "")
        print(f"{index}. {result.chunk_id}  score={result.score:.4f}")
        if page or section:
            print(f"   {page} :: {section}".rstrip(" :"))
        print(f"   {result.text[:240].replace(chr(10), ' ')}")


def _print_timings(
    *,
    embedding_seconds: float,
    retrieval_seconds: float,
    generation_seconds: float,
    total_seconds: float,
    first_token_seconds: float | None = None,
) -> None:
    print("Timings:")
    print(f"embedding: {_format_duration(embedding_seconds)}")
    print(f"retrieval: {_format_duration(retrieval_seconds)}")
    if first_token_seconds is not None:
        print(f"first_token: {_format_duration(first_token_seconds)}")
    print(f"generation: {_format_duration(generation_seconds)}")
    print(f"total: {_format_duration(total_seconds)}")


def _format_duration(seconds: float) -> str:
    return f"{seconds:.2f}s"


def _generate_answer(args: argparse.Namespace, messages: list[dict[str, str]]) -> GenerationResult:
    if args.stream:
        print("Answer:")
        return chat_with_ollama(
            messages,
            host=args.ollama_host,
            model=args.ollama_model,
            temperature=args.temperature,
            num_ctx=args.num_ctx,
            num_predict=args.max_tokens,
            stream=True,
            token_callback=_stream_token,
        )

    return chat_with_ollama(
        messages,
        host=args.ollama_host,
        model=args.ollama_model,
        temperature=args.temperature,
        num_ctx=args.num_ctx,
        num_predict=args.max_tokens,
    )


def _stream_token(token: str) -> None:
    print(token, end="", flush=True)


if __name__ == "__main__":
    main()
