# Lightweight Local RAG Q&A Chatbot

This repository builds a local Confluence-to-RAG pipeline:

1. preprocess Confluence HTML exports into Markdown
2. chunk Markdown into retrieval records
3. generate embeddings
4. build a persistent vector store
5. retrieve relevant chunks
6. generate grounded answers with Ollama

## Docs
- Full workflow: [docs/confluence-workflow.md](docs/confluence-workflow.md)
- Script order and runbook: [docs/confluence-script-order.md](docs/confluence-script-order.md)
- Testing guide: [docs/testing.md](docs/testing.md)
- Production deployment notes: [docs/production-deployment.md](docs/production-deployment.md)

## Quick Start
Create the virtual environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt
```

Put Confluence HTML export zip files in `data/raw/confluence/`, then run:

```powershell
python scripts\preprocess_confluence_exports.py
python scripts\chunk_confluence_exports.py
python scripts\embed_confluence_chunks.py
python scripts\build_confluence_vector_store.py
python scripts\ask_confluence.py "What does the architecture say about the execution layer?"
```

## Testing
Run the test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Layout
```text
CortexRAG/
|-- data/
|   |-- raw/              # Source exports
|   |-- processed/        # Markdown pages
|   `-- chunks/           # Retrieval-ready chunk JSONL
|-- docs/                 # Project documentation
|-- prompts/              # RAG prompt templates
|-- scripts/              # Pipeline entry-point scripts
|-- src/cortex_rag/       # Ingestion, retrieval, generation, CLI
|-- storage/
|   |-- embeddings/       # Embedded chunk JSONL
|   `-- chroma/           # Persistent Chroma or FAISS-backed vector store
`-- tests/
```
