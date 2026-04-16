# Confluence RAG Workflow

## Purpose
This document describes the full end-to-end workflow in CortexRAG: what each stage reads, what it writes, how the data shape changes, and what happens when a user asks a question.

The current pipeline is optimized for Confluence HTML space exports stored locally and answered through a local Ollama model. The primary query-time entry point is now `python -m cortex_rag ask ...`, with `scripts/ask_confluence.py` retained only as a compatibility wrapper.

## Workflow Summary
The repository turns Confluence exports into a grounded answer in six stages:

1. export Confluence spaces as HTML zip archives
2. preprocess HTML pages into Markdown files with preserved metadata
3. chunk Markdown into retrieval-ready JSONL records
4. generate embeddings for each chunk
5. build a persistent vector store from those embeddings
6. embed a user question, retrieve context, construct a prompt, and call Ollama

## Inputs, Outputs, and Defaults
Core paths and defaults live in `src/cortex_rag/config.py`.

Important defaults:

- raw exports: `data/raw/confluence/`
- processed Markdown: `data/processed/confluence/`
- chunk files: `data/chunks/confluence/`
- embedding files: `storage/embeddings/confluence/`
- vector store: `storage/chroma/`
- default embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- default vector collection: `confluence`
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
Entry point:

- `scripts/preprocess_confluence_exports.py`

Implementation:

- `src/cortex_rag/ingestion/confluence_html.py`

What happens:

1. the script scans `data/raw/confluence/` for zip archives
2. each zip is opened and HTML pages are collected
3. each HTML page is parsed with a standard-library HTML parser into a lightweight tree
4. the converter identifies the page body from Confluence-specific container nodes
5. Confluence presentation chrome is dropped
6. page content is rendered into Markdown
7. internal Confluence links are rewritten to local Markdown targets when possible
8. each page is written under `data/processed/confluence/<SPACE_KEY>/`

The converter preserves useful metadata in YAML front matter:

- `space_key`
- `space_name`
- `page_title`
- `page_type`
- `source_zip`
- `source_html`
- `breadcrumbs`
- `created_by`
- `created_on`

It also normalizes page naming:

- space landing pages become `space-index.md`
- regular pages become slug-plus-page-id names such as `architecture-3309569.md`
- duplicate slug collisions get numeric suffixes

Markdown rendering behavior:

- headings are preserved as Markdown headings
- paragraphs, links, lists, blockquotes, code blocks, and tables are converted
- decorative images are dropped
- external links stay external
- relative Confluence links are resolved against the export and mapped to generated Markdown files when possible

Output example:

- `data/processed/confluence/ASA/space-index.md`
- `data/processed/confluence/ASA/architecture-3309569.md`

## Stage 3: Chunking Markdown into Retrieval Records
Entry point:

- `scripts/chunk_confluence_exports.py`

Implementation:

- `src/cortex_rag/ingestion/confluence_chunks.py`

What happens:

1. the script scans `data/processed/confluence/`
2. each Markdown file is split into front matter and body
3. the Markdown body is parsed into a heading tree
4. the chunker walks that tree and builds heading-aware sections
5. large sections are split and very small adjacent sections are merged
6. link references inside the text are extracted and resolved to target pages where possible
7. chunk records are written as JSONL under `data/chunks/confluence/<SPACE_KEY>/`

Chunk sizing rules:

- target minimum: `200` words
- target maximum: `500` words
- small neighboring pieces may be merged if the merged chunk stays within the max
- oversized leaf sections are split by paragraph, then by plain-text word windows if needed

Each chunk record includes:

- `chunk_id`
- `page`
- `section`
- `headings`
- `text`
- `source`
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

Example record:

```json
{
  "chunk_id": "architecture-3309569:001",
  "page": "RAG Architecture",
  "section": "Embeddings",
  "headings": ["RAG Architecture", "Embeddings"],
  "text": "Embeddings convert text into vectors...",
  "source": "confluence",
  "space_key": "ASA",
  "word_count": 241,
  "links": [
    {
      "text": "Retrieval",
      "target_path": "retrieval-222.md",
      "target_page": "Retrieval"
    }
  ]
}
```

## Stage 4: Embedding Generation
Entry point:

- `scripts/embed_confluence_chunks.py`

Implementation:

- `src/cortex_rag/retrieval/confluence_embeddings.py`
- `src/cortex_rag/retrieval/embedding_utils.py`

What happens:

1. the script scans `data/chunks/confluence/`
2. it loads each chunk JSONL file
3. it extracts the chunk text fields
4. it loads a SentenceTransformer model
5. it encodes chunk text in batches
6. vectors are L2-normalized by default
7. the original chunk payload is written back out with embedding metadata and vector values
8. outputs are written to `storage/embeddings/confluence/<SPACE_KEY>/`

Important operational detail:

- the first run may download the embedding model unless it is already cached locally
- if the machine is offline, use a local model path with `--model`

Default behavior:

- model: `sentence-transformers/all-MiniLM-L6-v2`
- batch size: `32`
- normalization: enabled

Output fields added per record:

- `embedding_model`
- `embedding_dimensions`
- `embedding`

## Stage 5: Vector Store Build
Entry point:

- `scripts/build_confluence_vector_store.py`

Implementation:

- `src/cortex_rag/retrieval/vector_store.py`

What happens:

1. the script reads all embedding JSONL records from `storage/embeddings/confluence/`
2. it validates that all records use the same embedding model and vector size
3. it resolves the backend
4. it writes a persistent index
5. it writes a manifest file describing the built store

Backend selection:

- `--backend chroma` forces Chroma
- `--backend faiss` forces FAISS
- `--backend auto` tries Chroma first, then FAISS

Chroma build path:

- creates a persistent client rooted at `storage/chroma/`
- deletes any existing collection of the same name
- recreates and upserts records in batches
- stores metadata payload JSON alongside document text

FAISS build path:

- normalizes embeddings
- writes a flat inner-product FAISS index
- writes a parallel JSONL file of non-embedding record payloads

Manifest example:

```json
{
  "backend": "chroma",
  "collection_name": "confluence",
  "document_count": 57,
  "embedding_dimensions": 384,
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "distance_metric": "cosine"
}
```

This manifest is critical at query time because it tells the runtime:

- which backend to use
- which embedding model the index expects
- how many dimensions the query embedding must have

## Stage 6: Retrieval at Query Time
Entry points:

- `scripts/query_confluence_vector_store.py`
- `python -m cortex_rag similarity-search ...`

Implementation:

- `src/cortex_rag/retrieval/vector_store.py`

What happens when a query arrives:

1. the manifest is loaded from `storage/chroma/<collection>.manifest.json`
2. the question is embedded with the manifest embedding model unless explicitly overridden
3. raw nearest-neighbor search runs against Chroma or FAISS
4. the top candidate pool is reranked
5. near-duplicate chunks are removed
6. the final trimmed results are returned

The retrieval flow in this repo is not a plain nearest-neighbor return. It does three extra things:

### 1. Candidate expansion
It retrieves a broader candidate pool first:

- default raw candidate pool: `10`

### 2. Heuristic reranking
Results are boosted when:

- multiple hits agree on the same page
- section titles overlap with meaningful query keywords

The reranker stores debug-style metadata alongside results, including:

- `retrieval_similarity_score`
- `retrieval_rerank_score`
- `retrieval_page_hit_count`
- `retrieval_section_keyword_overlap`

### 3. Deduplication
Results are filtered for near duplicates by:

- normalized exact-text match
- heavy token overlap across chunks

Default trimmed result count:

- `5` for general retrieval
- `2` for `python -m cortex_rag ask ...` before prompt construction

## Stage 7: Prompt Construction
Entry point:

- called from `src/cortex_rag/generation/confluence_answering.py`

Implementation:

- `src/cortex_rag/generation/confluence_answering.py`
- `src/cortex_rag/generation/prompting.py`

What happens:

1. the prompt template is loaded from `prompts/confluence_rag.md`
2. retrieved chunks are formatted into a plain-text context block
3. the user question is combined with:
   - the answer mode
   - answer-style instructions
   - the retrieved source chunks
4. a two-message chat payload is built:
   - one `system` message from the prompt template
   - one `user` message containing question and retrieval context

Supported answer modes:

- `concise`
- `normal`
- `detailed`
- `bullet_summary`
- `technical`

Each retrieved chunk in the prompt includes:

- source number
- chunk ID
- page
- section
- score
- chunk text

## Stage 8: Answer Generation with Ollama
Entry point:

- `python -m cortex_rag ask ...`
- `scripts/ask_confluence.py` as a thin wrapper over the package CLI

Implementation:

- `src/cortex_rag/cli.py`
- `src/cortex_rag/generation/confluence_answering.py`
- `src/cortex_rag/generation/ollama_client.py`

What happens:

1. the CLI calls `answer_confluence_question(...)`
2. the package embeds the query
3. it retrieves and reranks context chunks
4. it stops early if no relevant chunks survive retrieval
5. it builds the final RAG chat messages
6. it calls Ollama through the Python client
7. the CLI prints the answer, sources, and timing breakdown

Default generation settings come from `src/cortex_rag/config.py` and environment variables:

- `OLLAMA_HOST`
- `OLLAMA_MODEL`
- `OLLAMA_NUM_CTX`
- `OLLAMA_TEMPERATURE`
- `OLLAMA_NUM_PREDICT`
- `RAG_ANSWER_MODE`

Streaming behavior:

- `--stream` prints tokens as they arrive
- time to first token is measured separately from total generation time

Timing breakdown reported by the CLI:

- embedding
- retrieval
- first token when streaming
- generation
- total

## What Gets Rebuilt When Data Changes
If a Confluence export changes, the practical rebuild path is:

1. rerun preprocessing
2. rerun chunking
3. rerun embeddings
4. rebuild the vector store

The downstream stages depend on the upstream artifacts:

- changed Markdown means chunk boundaries may change
- changed chunks mean embeddings must be regenerated
- changed embeddings mean the vector store must be rebuilt

## Routine Runtime Paths
Two common runtime modes exist in this repo:

### Ingestion and indexing mode
Used when refreshing the knowledge base.

Flow:

1. process zip exports
2. chunk Markdown
3. generate embeddings
4. rebuild the vector store

### Query and answer mode
Used after the vector store already exists.

Flow:

1. embed the user question
2. retrieve reranked chunks
3. build a grounded prompt
4. generate an answer with Ollama

## Practical Constraints
- Embedding-model downloads may require network access on the first run.
- Query embeddings must match the dimensions recorded in the vector-store manifest.
- The in-process SentenceTransformer cache only helps long-lived Python processes, not separate one-shot script runs.
- `answer_confluence_question(...)` does not call Ollama if retrieval returns no usable context.
- Rebuilding the vector store replaces the existing collection for the selected name.

## Relevant Code
- preprocessing: `src/cortex_rag/ingestion/confluence_html.py`
- chunking: `src/cortex_rag/ingestion/confluence_chunks.py`
- embeddings: `src/cortex_rag/retrieval/confluence_embeddings.py`
- vector store and retrieval: `src/cortex_rag/retrieval/vector_store.py`
- end-to-end answer flow: `src/cortex_rag/generation/confluence_answering.py`
- prompt building: `src/cortex_rag/generation/prompting.py`
- Ollama client: `src/cortex_rag/generation/ollama_client.py`
- CLI entry points: `src/cortex_rag/cli.py`
- compatibility wrapper: `scripts/ask_confluence.py`
