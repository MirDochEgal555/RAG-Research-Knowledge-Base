"""Thin Ollama client wrapper for local generation."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from ollama import Client

from cortex_rag.config import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_KEEP_ALIVE,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_NUM_CTX,
    DEFAULT_OLLAMA_NUM_PREDICT,
    DEFAULT_OLLAMA_TEMPERATURE,
)


Message = Mapping[str, Any]


@dataclass(frozen=True)
class GenerationResult:
    """Normalized response payload from an Ollama chat call."""

    model: str
    content: str
    first_token_seconds: float | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    done_reason: str | None = None


def chat_with_ollama(
    messages: Sequence[Message],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE,
    num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
    num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT,
    keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE,
    stream: bool = False,
    token_callback: Callable[[str], None] | None = None,
    client_factory: Callable[..., Any] = Client,
) -> GenerationResult:
    """Send a chat request to Ollama and normalize the response."""

    client = client_factory(host=host)
    request_started_at = perf_counter()
    response = client.chat(
        model=model,
        messages=list(messages),
        stream=stream,
        options={
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
        keep_alive=keep_alive,
    )
    if stream:
        return _consume_streaming_response(
            response,
            fallback_model=model,
            request_started_at=request_started_at,
            token_callback=token_callback,
        )

    message = getattr(response, "message", None)
    content = str(getattr(message, "content", "")).strip()
    return GenerationResult(
        model=str(getattr(response, "model", model)),
        content=content,
        first_token_seconds=0.0 if content else None,
        prompt_eval_count=_optional_int(getattr(response, "prompt_eval_count", None)),
        eval_count=_optional_int(getattr(response, "eval_count", None)),
        done_reason=_optional_str(getattr(response, "done_reason", None)),
    )


def _consume_streaming_response(
    responses: Any,
    *,
    fallback_model: str,
    request_started_at: float,
    token_callback: Callable[[str], None] | None,
) -> GenerationResult:
    chunks: list[str] = []
    first_token_seconds: float | None = None
    final_response: Any = None

    for response in responses:
        final_response = response
        message = getattr(response, "message", None)
        content_chunk = str(getattr(message, "content", "") or "")
        if content_chunk and first_token_seconds is None:
            first_token_seconds = perf_counter() - request_started_at
        if content_chunk:
            chunks.append(content_chunk)
            if token_callback is not None:
                token_callback(content_chunk)

    content = "".join(chunks).strip()
    return GenerationResult(
        model=str(getattr(final_response, "model", fallback_model)),
        content=content,
        first_token_seconds=first_token_seconds,
        prompt_eval_count=_optional_int(getattr(final_response, "prompt_eval_count", None)),
        eval_count=_optional_int(getattr(final_response, "eval_count", None)),
        done_reason=_optional_str(getattr(final_response, "done_reason", None)),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
