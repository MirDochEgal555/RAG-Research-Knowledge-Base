# Testing Guide

## Purpose

This document describes what is tested in the current CortexRAG repository, how to run those tests, and what is not yet covered by automation.

The repo currently has:

- a Python pytest suite for ingestion, retrieval, graph, API, and CLI behavior
- no frontend unit or browser automation tests yet
- no live Ollama integration tests in the automated suite

## Current Test Scope

The Python suite covers the main package layers:

- Confluence HTML preprocessing
- Markdown chunking
- embedding helpers
- vector-store build and retrieval behavior
- grounded answer construction
- Ollama client normalization
- CLI entry points
- graph artifact build and neighborhood extraction
- API serialization and FastAPI route wiring
- legacy script wrappers that now delegate to the package CLI

Current test files under `tests/`:

- `test_confluence_html.py`
- `test_confluence_chunks.py`
- `test_confluence_embeddings.py`
- `test_embedding_utils.py`
- `test_confluence_vector_store.py`
- `test_generation.py`
- `test_confluence_answering.py`
- `test_cli.py`
- `test_api_serializers.py`
- `test_api_app.py`
- `test_confluence_graph.py`
- `test_build_confluence_graph.py`
- `test_ask_confluence.py`

## What The Suite Specifically Locks Down

### Ingestion and chunking

- Confluence HTML export parsing
- Markdown conversion behavior
- heading-aware chunk construction
- chunk metadata preservation

### Embeddings and retrieval

- embedding normalization helpers
- vector-store build behavior
- retrieval result shaping
- retrieval metadata and score handling

### Generation and answer flow

- missing and empty prompt templates
- blank user questions rejected before prompt construction
- empty retrieval results returned to the package-level answer flow
- retrieved chunks with incomplete metadata
- streaming Ollama responses that never yield usable content
- timing output when first-token latency is absent

### CLI and script wrappers

- `python -m cortex_rag similarity-search ...` output formatting
- `python -m cortex_rag ask ...` output formatting
- `python -m cortex_rag build-graph ...` summary output
- `python -m cortex_rag build-vector-store --with-graph ...` combined build behavior
- `scripts/ask_confluence.py` remaining a thin wrapper over the package CLI
- `scripts/build_confluence_graph.py` remaining a thin wrapper over the package CLI

### API and graph behavior

- API serialization for search, answer, and graph neighborhood payloads
- FastAPI route wiring for `/health`, `/search`, `/answer`, and `/graph/neighborhood`
- persisted document/chunk graph build behavior
- graph neighborhood expansion from retrieved chunk seeds

## What Is Not Covered Yet

The current automated suite does not cover:

- real browser interaction against the frontend
- frontend component or visual regression tests
- end-to-end UI tests through a running API backend
- live Ollama calls against a real local model
- deployment smoke tests

That means frontend changes should still be verified with at least a manual build and a manual UI smoke test.

## Test Environment Expectations

Install the development dependencies first:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt
pip install -e .
```

Important dependency note:

- `requirements-dev.txt` includes `httpx`
- `requirements.txt` includes `fastapi`

This matters because some API tests are conditional and skip themselves when optional HTTP test dependencies are missing.

## Run Commands

Run the full Python suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run ingestion-focused coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_confluence_html.py tests\test_confluence_chunks.py tests\test_confluence_embeddings.py
```

Run retrieval and generation coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_embedding_utils.py tests\test_confluence_vector_store.py tests\test_generation.py tests\test_confluence_answering.py
```

Run CLI and script-wrapper coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_cli.py tests\test_ask_confluence.py tests\test_build_confluence_graph.py
```

Run API-focused coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_serializers.py tests\test_api_app.py
```

Run graph-focused coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_confluence_graph.py
```

## Optional API Test Behavior

`tests/test_api_app.py` behaves differently depending on installed packages:

- if `fastapi` is missing, it verifies that app creation fails with a clear error
- if `fastapi` and `httpx` are both installed, it also runs the FastAPI route tests with `TestClient`

So skipped API tests are not necessarily a bug. They can simply mean the optional HTTP test stack is not installed in the current environment.

## Frontend Verification

There are currently no frontend automated tests in `frontend/`.

The minimum frontend verification step today is a production build:

```powershell
cd frontend
npm install
npm run build
```

For UI changes, also run a manual smoke test with the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn --app-dir src cortex_rag.api:create_app --factory --reload
cd frontend
npm run dev
```

Then verify at least:

- the page loads
- `GET /health` succeeds
- a query returns search results
- a query returns a graph neighborhood
- a query returns a grounded answer
- node selection updates the detail panel

## Pytest Configuration Notes

The current pytest configuration lives in [pytest.ini](/c:/Users/robin.keim/Documents/CortexRAG/pytest.ini).

Important behavior:

- test discovery is limited to `tests/`
- discovery skips `.venv`, temp directories, data directories, notebooks, prompts, scripts, and `src/`
- pytest cache provider is disabled
- pytest's built-in `tmpdir` plugin is disabled

## Temporary Directory Behavior

`tests/conftest.py` provides a custom `tmp_path` fixture.

Instead of using pytest's standard temp directory plugin, tests create repo-local temporary directories under:

- `scratch_pytest/`

Those directories are cleaned up after each test run.

## Practical Guidance

Use the suite in three layers:

1. run targeted test files while changing one subsystem
2. run `pytest -q` before considering the work complete
3. if the change affects the UI, also run the frontend build and a manual browser smoke test

This is the right current balance for the repo because the Python core is well covered, while the frontend still relies on build checks and manual verification.
