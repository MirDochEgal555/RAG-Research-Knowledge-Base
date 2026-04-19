# Confluence RAG Workflow

## Purpose

This document describes the current end-to-end Confluence pipeline in CortexRAG: what each stage reads, what it writes, and which entry points are now considered primary.

The pipeline has two distinct modes:

- indexing mode: turn Confluence exports into persistent retrieval and graph artifacts
- runtime mode: answer questions and drive the UI from those persisted artifacts

## Current Entry Points

The repo now uses a mixed model:

- preprocessing, chunking, and embedding generation are still script-first
- vector-store build, graph build, retrieval, and answering have package CLI entry points
- `scripts/ask_confluence.py` and `scripts/build_confluence_graph.py` are compatibility wrappers, not the preferred interface

Primary commands today:

```powershell
python scripts\preprocess_confluence_exports.py
python scripts\chunk_confluence_exports.py
python scripts\embed_confluence_chunks.py
python -m cortex_rag build-vector-store --with-graph
python -m cortex_rag similarity-search "your question"
python -m cortex_rag ask "your question"
```

For the UI stack after indexing:

```powershell
.\.venv\Scripts\python.exe -m uvicorn --app-dir src cortex_rag.api:create_app --factory --reload
cd frontend
npm run dev
```

## Workflow Summary

The repository turns Confluence HTML exports into three runtime products:

- a persistent vector store
- a persisted document/chunk graph artifact
- grounded answers and graph neighborhoods at query time

The full indexing path is:

1. export Confluence spaces as HTML zip archives
2. preprocess HTML pages into Markdown
3. chunk Markdown into retrieval-ready JSONL
4. generate embeddings
5. build a persistent vector store
6. build a persisted document/chunk graph artifact

The query-time path is:

1. embed the user question
2. retrieve and rerank matching chunks
3. optionally build a grounded answer with Ollama
4. optionally build a graph neighborhood for the UI

## Inputs, Outputs, and Defaults

Core defaults live in [src/cortex_rag/config.py](/c:/Users/robin.keim/Documents/CortexRAG/src/cortex_rag/config.py).

Important defaults:

- raw exports: `data/raw/confluence/`
- processed Markdown: `data/processed/confluence/`
- chunk files: `data/chunks/confluence/`
- embedding files: `storage/embeddings/confluence/`
- vector store directory: `storage/chroma/`
- graph artifact: `storage/chroma/<collection>.graph.json`
- default vector collection: `confluence`
- default embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- default Ollama host: `http://127.0.0.1:11434`
- default Ollama model: `llama3.2:3b`
- default prompt template: `prompts/confluence_rag.md`

## Stage 1: Raw Confluence Exports

Expected input:

- one `.zip` file per Confluence space
- stored under `data/raw/confluence/`

Example:

- `data/raw/confluence/ASA_2026-04-16.zip`

The preprocessing step infers the space key from the zip filename stem before the first underscore. For `ASA_2026-04-16.zip`, the space key is `ASA`.

## Stage 2: HTML Preprocessing to Markdown

Primary entry point:

- `python scripts\preprocess_confluence_exports.py`

Implementation:

- `src/cortex_rag/ingestion/confluence_html.py`

What happens:

1. scan `data/raw/confluence/` for zip archives
2. parse exported HTML pages
3. strip Confluence chrome and preserve page content
4. convert page bodies to Markdown
5. write Markdown under `data/processed/confluence/<SPACE_KEY>/`

Preserved metadata in front matter includes:

- `space_key`
- `space_name`
- `page_title`
- `page_type`
- `source_zip`
- `source_html`
- `breadcrumbs`
- `created_by`
- `created_on`

Output examples:

- `data/processed/confluence/ASA/space-index.md`
- `data/processed/confluence/ASA/architecture-3309569.md`

## Stage 3: Chunking Markdown into Retrieval Records

Primary entry point:

- `python scripts\chunk_confluence_exports.py`

Implementation:

- `src/cortex_rag/ingestion/confluence_chunks.py`

What happens:

1. scan `data/processed/confluence/`
2. split front matter and Markdown body
3. parse the heading structure
4. create heading-aware chunks
5. merge or split sections to keep chunk sizes usable
6. extract link references where possible
7. write chunk JSONL under `data/chunks/confluence/<SPACE_KEY>/`

Each chunk record includes fields such as:

- `chunk_id`
- `page`
- `section`
- `headings`
- `text`
- `space_key`
- `space_name`
- `page_type`
- `source_path`
- `source_html`
- `breadcrumbs`
- `created_by`
- `created_on`
- `word_count`
- `links`

## Stage 4: Embedding Generation

Primary entry point:

- `python scripts\embed_confluence_chunks.py`

Implementation:

- `src/cortex_rag/retrieval/confluence_embeddings.py`
- `src/cortex_rag/retrieval/embedding_utils.py`

What happens:

1. scan `data/chunks/confluence/`
2. load chunk JSONL records
3. encode chunk text with SentenceTransformers
4. normalize vectors by default
5. write embedding-enriched JSONL to `storage/embeddings/confluence/`

Default behavior:

- model: `sentence-transformers/all-MiniLM-L6-v2`
- batch size: `32`
- normalization: enabled

Additional output fields include:

- `embedding_model`
- `embedding_dimensions`
- `embedding`

Operational note:

- the first run may download the embedding model if it is not already cached locally

## Stage 5: Vector Store Build

Preferred entry point:

- `python -m cortex_rag build-vector-store`

Legacy script entry point:

- `python scripts\build_confluence_vector_store.py`

Implementation:

- `src/cortex_rag/retrieval/vector_store.py`
- `src/cortex_rag/cli.py`

What happens:

1. read all embedding JSONL records from `storage/embeddings/confluence/`
2. validate a single embedding model and vector size across the corpus
3. build a persistent Chroma or FAISS-backed store
4. write a manifest describing the built store

Backend selection:

- `--backend chroma` forces Chroma
- `--backend faiss` forces FAISS
- `--backend auto` tries Chroma first, then FAISS

Primary outputs:

- `storage/chroma/<collection>.manifest.json`
- backend-specific vector-store files under `storage/chroma/`

Preferred combined build:

```powershell
python -m cortex_rag build-vector-store --with-graph
```

That command builds the vector store and immediately writes the graph artifact as well.

## Stage 6: Graph Artifact Build

Preferred entry point:

- `python -m cortex_rag build-graph`

Compatibility wrapper:

- `python scripts\build_confluence_graph.py`

Implementation:

- `src/cortex_rag/graph/confluence_graph.py`
- `src/cortex_rag/cli.py`

What happens:

1. read the embedding JSONL records
2. create one `document` node per source page
3. create one `chunk` node per chunk record
4. create `belongs_to` edges from document to chunk
5. compute offline `similar_to` edges between chunks from cosine similarity
6. write `storage/chroma/<collection>.graph.json`

Current graph rules:

- node types: `document`, `chunk`
- edge types: `belongs_to`, `similar_to`
- document identity prefers `source_path`
- chunk identity comes from `chunk_id`
- similarity edges are limited by `--similarity-top-k` and `--similarity-threshold`

This graph artifact is required by the UI backend for `/graph/neighborhood`.

## Stage 7: Retrieval at Query Time

Preferred entry point:

- `python -m cortex_rag similarity-search "question"`

Legacy script entry point:

- `python scripts\query_confluence_vector_store.py "question"`

Implementation:

- `src/cortex_rag/retrieval/vector_store.py`
- `src/cortex_rag/cli.py`

What happens:

1. load the vector-store manifest
2. embed the question with the recorded embedding model unless overridden
3. run nearest-neighbor retrieval against Chroma or FAISS
4. rerank the candidate set
5. remove near-duplicate chunks
6. return the final trimmed results

Default retrieval shaping:

- candidate pool: `10`
- final results for search: `5`
- final results for answer generation: `2`

The retriever adds debug-style metadata such as:

- `retrieval_similarity_score`
- `retrieval_rerank_score`
- `retrieval_page_hit_count`
- `retrieval_section_keyword_overlap`

## Stage 8: Prompt Construction

Entry point:

- called internally from `src/cortex_rag/generation/confluence_answering.py`

Implementation:

- `src/cortex_rag/generation/confluence_answering.py`
- `src/cortex_rag/generation/prompting.py`

What happens:

1. load `prompts/confluence_rag.md`
2. format retrieved chunks into a grounded context block
3. combine question, answer mode, and source chunks
4. build a two-message chat payload for Ollama

Supported answer modes:

- `concise`
- `normal`
- `detailed`
- `bullet_summary`
- `technical`

## Stage 9: Answer Generation with Ollama

Preferred entry point:

- `python -m cortex_rag ask "question"`

Compatibility wrapper:

- `python scripts\ask_confluence.py "question"`

Implementation:

- `src/cortex_rag/cli.py`
- `src/cortex_rag/generation/confluence_answering.py`
- `src/cortex_rag/generation/ollama_client.py`

What happens:

1. embed the query
2. retrieve and rerank context
3. stop early if no usable context survives retrieval
4. build grounded prompt messages
5. call Ollama
6. print the answer, sources, and timing breakdown

Important behavior:

- if retrieval returns no usable context, Ollama is not called
- `--stream` prints tokens as they arrive
- streaming records time to first token separately

Timing breakdown:

- embedding
- retrieval
- first token when streaming
- generation
- total

## Stage 10: UI Backend and Frontend Runtime

Backend entry point:

```powershell
.\.venv\Scripts\python.exe -m uvicorn --app-dir src cortex_rag.api:create_app --factory --reload
```

Frontend entry point:

```powershell
cd frontend
npm run dev
```

Backend endpoints:

- `GET /health`
- `POST /search`
- `POST /answer`
- `POST /graph/neighborhood`

Runtime behavior:

- `/health` warms the graph artifact and embedding model
- `/search` wraps retrieval only
- `/answer` wraps the grounded answer flow
- `/graph/neighborhood` retrieves seed chunks, loads the persisted graph, and returns a focused neighborhood for the UI

See [ui-usage.md](./ui-usage.md) for the operator guide to the current interface.

## What Gets Rebuilt When Data Changes

If a Confluence export changes, the practical rebuild path is:

1. rerun preprocessing
2. rerun chunking
3. rerun embeddings
4. rebuild the vector store
5. rebuild the graph artifact

Short version:

```powershell
python scripts\preprocess_confluence_exports.py
python scripts\chunk_confluence_exports.py
python scripts\embed_confluence_chunks.py
python -m cortex_rag build-vector-store --with-graph
```

The downstream dependencies are strict:

- changed Markdown can change chunk boundaries
- changed chunks require new embeddings
- changed embeddings require a new vector store
- changed embeddings also require a new graph artifact

## Routine Runtime Paths

### Indexing mode

Used when refreshing the knowledge base:

1. preprocess exports
2. chunk Markdown
3. generate embeddings
4. build vector store
5. build graph artifact

### CLI query mode

Used after indexing is complete:

1. embed user question
2. retrieve reranked chunks
3. optionally generate grounded answer with Ollama

### UI mode

Used after indexing is complete:

1. start the FastAPI backend
2. start the frontend
3. load the graph neighborhood, answer, and search endpoints from the browser

## Practical Constraints

- embedding-model downloads may require network access on the first run
- query embeddings must match the dimensions recorded in the manifest
- rebuilding the vector store replaces the existing collection for the selected name
- the graph artifact is not auto-rebuilt unless you run `build-graph` or `build-vector-store --with-graph`
- `python -m cortex_rag ask ...` depends on a working Ollama runtime and configured model
- the UI backend depends on both the vector-store manifest and the graph artifact

## Relevant Code

- preprocessing: `src/cortex_rag/ingestion/confluence_html.py`
- chunking: `src/cortex_rag/ingestion/confluence_chunks.py`
- embeddings: `src/cortex_rag/retrieval/confluence_embeddings.py`
- vector store and retrieval: `src/cortex_rag/retrieval/vector_store.py`
- graph model and persistence: `src/cortex_rag/graph/confluence_graph.py`
- answer flow: `src/cortex_rag/generation/confluence_answering.py`
- prompt building: `src/cortex_rag/generation/prompting.py`
- Ollama client: `src/cortex_rag/generation/ollama_client.py`
- API backend: `src/cortex_rag/api/app.py`
- CLI entry points: `src/cortex_rag/cli.py`
