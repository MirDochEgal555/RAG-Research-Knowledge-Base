# Confluence Script Order

## Purpose
This is the operator runbook for the current Confluence pipeline. It answers one question only: which script to run, in which order, and when.

## Standard Order
Run the scripts in this order from the repository root:

1. `python scripts\preprocess_confluence_exports.py`
2. `python scripts\chunk_confluence_exports.py`
3. `python scripts\embed_confluence_chunks.py`
4. `python scripts\build_confluence_vector_store.py`
5. `python scripts\query_confluence_vector_store.py "<question>"`
6. `python -m cortex_rag ask "<question>"`

Only the first four steps are required to refresh the knowledge base. The last two are query-time commands.

## What Each Script Expects and Produces

### 1. Preprocess raw Confluence exports
Run:

```powershell
python scripts\preprocess_confluence_exports.py
```

Reads:

- `data/raw/confluence/*.zip`

Writes:

- `data/processed/confluence/<SPACE_KEY>/*.md`

Run this when:

- you add a new Confluence HTML export zip
- an existing export zip changed

### 2. Chunk processed Markdown
Run:

```powershell
python scripts\chunk_confluence_exports.py
```

Reads:

- `data/processed/confluence/**/*.md`

Writes:

- `data/chunks/confluence/<SPACE_KEY>/*.jsonl`

Run this after:

- preprocessing

### 3. Generate embeddings
Run:

```powershell
python scripts\embed_confluence_chunks.py
```

Reads:

- `data/chunks/confluence/<SPACE_KEY>/*.jsonl`

Writes:

- `storage/embeddings/confluence/<SPACE_KEY>/*.jsonl`

Run this after:

- chunking

Useful variants:

```powershell
python scripts\embed_confluence_chunks.py --model sentence-transformers/all-mpnet-base-v2
python scripts\embed_confluence_chunks.py --batch-size 16 --device cpu
python scripts\embed_confluence_chunks.py --no-normalize
```

### 4. Build the persistent vector store
Run:

```powershell
python scripts\build_confluence_vector_store.py
```

Reads:

- `storage/embeddings/confluence/**/*.jsonl`

Writes:

- `storage/chroma/confluence.manifest.json`
- backend-specific vector-store files under `storage/chroma/`

Run this after:

- embeddings finish successfully

Useful variants:

```powershell
python scripts\build_confluence_vector_store.py --backend chroma
python scripts\build_confluence_vector_store.py --backend faiss
python scripts\build_confluence_vector_store.py --collection asa-dev
```

### 5. Inspect retrieval results
Run:

```powershell
python scripts\query_confluence_vector_store.py "What does the architecture say about the execution layer?"
```

Reads:

- the built vector store in `storage/chroma/`
- the embedding model defined in the manifest, unless overridden

Writes:

- nothing persistent

Use this when:

- you want to inspect raw retrieval quality before involving Ollama
- you want to tune `candidate-k`, `top-k`, or `min-score`

Useful variants:

```powershell
python scripts\query_confluence_vector_store.py "How are leads qualified?" --candidate-k 10 --top-k 3
python scripts\query_confluence_vector_store.py "How are leads qualified?" --min-score 0.7
python scripts\query_confluence_vector_store.py "How are leads qualified?" --model C:\models\all-MiniLM-L6-v2
```

### 6. Ask a full RAG question
Run:

```powershell
python -m cortex_rag ask "What does the architecture say about the execution layer?"
```

Reads:

- the built vector store in `storage/chroma/`
- `prompts/confluence_rag.md`
- Ollama runtime on the configured host

Writes:

- nothing persistent

Use this when:

- the vector store already exists
- you want a grounded answer instead of only retrieval results

Useful variants:

```powershell
python -m cortex_rag ask "How are leads qualified?" --mode technical
python -m cortex_rag ask "Summarize the architecture" --mode bullet_summary
python -m cortex_rag ask "What does the architecture say?" --top-k 2 --num-ctx 4096 --max-tokens 80
python -m cortex_rag ask "What does the architecture say?" --stream --max-tokens 80
python -m cortex_rag ask "How are leads qualified?" --ollama-model mistral:latest --temperature 0.1
```

Compatibility note:

- `scripts\ask_confluence.py` still works, but it now forwards directly to `python -m cortex_rag ask ...`.

## Refresh Scenarios

### New or changed Confluence export
Run all indexing steps again:

```powershell
python scripts\preprocess_confluence_exports.py
python scripts\chunk_confluence_exports.py
python scripts\embed_confluence_chunks.py
python scripts\build_confluence_vector_store.py
```

### No content change, just ask a question
Run only:

```powershell
python -m cortex_rag ask "<question>"
```

### Retrieval looks wrong and you want to debug before generation
Run:

```powershell
python scripts\query_confluence_vector_store.py "<question>"
```

## Recommended First-Time Setup Flow
If you are setting up the repo on a fresh machine:

1. create and activate `.venv`
2. install `requirements-dev.txt`
3. place Confluence zip exports in `data/raw/confluence/`
4. run preprocess
5. run chunking
6. run embeddings
7. run vector-store build
8. run a retrieval query
9. run `python -m cortex_rag ask ...` once Ollama is available

## Common Mistakes
- Running `chunk_confluence_exports.py` before preprocessing. There will be no Markdown input to chunk.
- Running `build_confluence_vector_store.py` before embeddings exist. The build step will fail because there are no embedding records.
- Changing the embedding model and then querying an old index without rebuilding it. Query vectors must match the manifest dimensions and model assumptions.
- Expecting `python -m cortex_rag ask ...` to work before the vector store exists.
- Expecting `python -m cortex_rag ask ...` to work if Ollama is not running or the configured model is missing.

## Minimal Daily Commands
To refresh the corpus:

```powershell
python scripts\preprocess_confluence_exports.py
python scripts\chunk_confluence_exports.py
python scripts\embed_confluence_chunks.py
python scripts\build_confluence_vector_store.py
```

To ask a question afterward:

```powershell
python -m cortex_rag ask "<question>"
```
