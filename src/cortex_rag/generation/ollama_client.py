"""Thin Ollama client wrapper for local generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ollama import Client

from cortex_rag.config import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_KEEP_ALIVE,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_NUM_CTX,
    DEFAULT_OLLAMA_TEMPERATURE,
)


Message = Mapping[str, Any]


@dataclass(frozen=True)
class GenerationResult:
    """Normalized response payload from an Ollama chat call."""

    model: str
    content: str
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
    keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE,
    client_factory: Callable[..., Any] = Client,
) -> GenerationResult:
    """Send a non-streaming chat request to Ollama and normalize the response."""

    client = client_factory(host=host)
    response = client.chat(
        model=model,
        messages=list(messages),
        stream=False,
        options={
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
        keep_alive=keep_alive,
    )

    message = getattr(response, "message", None)
    content = str(getattr(message, "content", "")).strip()
    return GenerationResult(
        model=str(getattr(response, "model", model)),
        content=content,
        prompt_eval_count=_optional_int(getattr(response, "prompt_eval_count", None)),
        eval_count=_optional_int(getattr(response, "eval_count", None)),
        done_reason=_optional_str(getattr(response, "done_reason", None)),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
