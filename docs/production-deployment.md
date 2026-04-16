# Production Deployment Guide

## Purpose
This document describes how to move the current local CortexRAG setup to a production-style server deployment without changing the core workflow:

1. preprocess Confluence exports
2. chunk Markdown pages
3. generate embeddings
4. build a persistent vector store
5. retrieve context
6. generate answers with a local model via Ollama

The goal is to keep local development and server deployment aligned so that production becomes a configuration and infrastructure change, not a rewrite.

## Current Project Shape
The repository already supports the retrieval side of the pipeline:

- ingestion from Confluence HTML exports
- chunk generation under `data/chunks/`
- embedding generation under `storage/embeddings/`
- persistent vector store creation under `storage/chroma/`
- context retrieval via `scripts/query_confluence_vector_store.py`
- end-to-end retrieval plus generation via `scripts/ask_confluence.py`

The repository also includes a local Ollama integration path. Production planning should assume:

- Ollama will be the local inference runtime
- generation code should live behind a small adapter in `src/cortex_rag/generation/`
- runtime configuration should come from environment variables or a small config layer
- query-time embedding models should be preloaded inside a long-lived process to avoid repeated cold starts

## Recommended Production Architecture
For the first server deployment, keep the architecture simple:

- one application process for the Python RAG service
- one local Ollama service on the same server
- one persistent data directory for processed data, embeddings, and vector-store files
- one reverse proxy in front of the application if external access is needed

Recommended request flow:

1. user sends a question to the application
2. application embeds the question
3. application retrieves relevant chunks from the vector store
4. application builds a prompt from the retrieved context
5. application sends the prompt to Ollama on the same host
6. application returns the answer and optional source references

For the first production version, avoid splitting this across multiple machines unless there is a clear need. Keeping the app and Ollama on the same host reduces latency and operational complexity.

## Deployment Modes
### Recommended first production mode
- Linux server
- Python virtual environment
- Ollama installed as a local service
- app started with `systemd`
- reverse proxy with Nginx or Caddy

### Acceptable later mode
- Docker or Docker Compose
- mounted persistent volumes for `data/` and `storage/`
- separate service containers for app and reverse proxy

Containers are useful later, but they are not required for the first stable deployment. A simple service-based deployment is easier to debug.

## Server Sizing
Choose the model based on the server hardware, not local convenience.

Baseline guidance:

- CPU-only server: start with a small model such as `llama3.2:3b`
- modest GPU server: test a stronger model only after measuring latency and memory use
- low-memory server: avoid large context windows and large models

The current local machine already has:

- `llama3.2:3b`
- `mistral:latest`

For the first production rollout, pin one model explicitly instead of using `latest`.

Recommended initial production model:

- `llama3.2:3b`

Reasons:

- already present in your local workflow
- small enough for conservative hardware
- suitable for retrieval-grounded answering

## Production File Layout
Keep application code and mutable data separate.

Example layout:

```text
/opt/cortexrag/app/            # checked-out repository
/opt/cortexrag/venv/           # Python virtual environment
/var/lib/cortexrag/data/       # raw and processed documents if stored on server
/var/lib/cortexrag/storage/    # embeddings and vector store
/etc/cortexrag/.env            # deployment environment variables
/var/log/cortexrag/            # application logs if not using journal only
```

If you keep the repository structure unchanged, make sure the server deployment either:

- stores mutable project data directly under the repo and persists that directory, or
- overrides paths in config so data is stored outside the repo

The second option is safer for production.

## What Must Be Configurable
Before production, these values should not be hardcoded:

- Ollama host
- Ollama model name
- Ollama request timeout
- Ollama context window
- generation temperature
- vector-store persist directory
- collection name
- embedding model name
- log level

Recommended environment variables:

```env
CORTEX_RAG_ENV=production
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=192
OLLAMA_TEMPERATURE=0.2
RAG_ANSWER_MODE=normal
VECTOR_DB_DIR=/var/lib/cortexrag/storage/chroma
VECTOR_COLLECTION=confluence
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
LOG_LEVEL=INFO
```

Even if some of these are not implemented yet, this should be the configuration target.

## Data and Persistence Requirements
Production will need persistent storage for:

- raw Confluence exports if ingestion happens on the server
- processed Markdown under `data/processed/`
- chunk files under `data/chunks/`
- embedding JSONL files under `storage/embeddings/`
- vector-store files under `storage/chroma/`

At minimum, the vector-store and embedding outputs must persist across restarts.

Do not treat `storage/chroma/` as disposable unless you are intentionally rebuilding the index.

## Keeping the Embedding Model Hot
SentenceTransformer load time can dominate request latency if every query starts a fresh Python process.

Production guidance:

- run retrieval inside a long-lived application process
- preload the embedding model once during startup
- reuse the cached encoder for later queries in the same process

The current retrieval package exposes:

```python
from cortex_rag.retrieval import preload_sentence_transformer

preload_sentence_transformer(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    device="cpu",
)
```

Important constraint:

- this cache is in-process only
- one-shot script invocations do not share it across runs
- a service, API process, or worker process does

## Ingestion Strategy in Production
There are two valid approaches.

### Option A: Build data on the server
Use this when the server is the canonical runtime environment.

Flow:

1. upload new Confluence export zip files
2. run preprocessing
3. run chunking
4. run embeddings
5. rebuild the vector store

Pros:

- single source of truth
- no artifact shipping step

Cons:

- server needs all Python and model dependencies for ingestion
- rebuild jobs consume compute on the production machine

### Option B: Build data locally or in CI, then ship artifacts
Use this when production should stay focused on serving traffic.

Flow:

1. preprocess, chunk, embed, and build locally or in CI
2. copy generated artifacts to the server
3. restart or reload the application if needed

Pros:

- production box stays simpler
- faster rollback by swapping known-good artifacts

Cons:

- deployment artifact handling becomes more important

For the first production rollout, Option B is usually cleaner.

## Ollama Setup on the Server
Install Ollama on the server and ensure it starts automatically.

Production expectations:

- Ollama listens only on localhost unless there is a deliberate reason otherwise
- the required model is pulled during deployment, not on first live request
- model tag is pinned exactly

Server verification commands:

```bash
ollama --version
ollama list
ollama run llama3.2:3b
```

If Ollama and the application run on the same host, use:

```env
OLLAMA_HOST=http://127.0.0.1:11434
```

Do not expose the Ollama API directly to the public internet.

## Application Setup on the Server
Recommended baseline steps:

1. install Python 3.11 or 3.12 unless you have a strong reason to stay on 3.13
2. create a dedicated virtual environment
3. install `requirements-dev.txt` or a future production requirements file
4. set environment variables in a managed `.env` file or service definition
5. start the app with a service manager

Example baseline setup:

```bash
python3.12 -m venv /opt/cortexrag/venv
source /opt/cortexrag/venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements-dev.txt
```

## Service Management
Use a process manager. Do not rely on a manually opened shell session.

Typical Linux choice:

- `systemd` for the app
- `systemd` for Ollama if not already installed that way

Application service responsibilities:

- start automatically on boot
- restart on failure
- read environment variables from a single controlled source
- write logs to journald or a defined log directory

## Reverse Proxy and Network Exposure
If users will access the service remotely:

- place Nginx or Caddy in front of the app
- expose only the application endpoint
- keep Ollama bound to localhost
- terminate TLS at the reverse proxy
- restrict access with network policy, auth, or both

Do not expose:

- raw vector-store files
- Ollama directly
- ingestion-only admin endpoints without authentication

## Security Requirements
Before production, cover these basics:

- run the app under a dedicated non-admin user
- store secrets outside the repository
- restrict file permissions on `.env` and data directories
- expose only the required app port
- keep Ollama on localhost
- validate any uploaded files if ingestion is exposed through an API
- log enough for audit and debugging, but do not log full sensitive prompts or documents unless required

If the Confluence content includes confidential internal material, treat the server as a trusted internal system and protect it accordingly.

## Logging and Observability
At minimum, production logs should capture:

- application startup
- model name in use
- vector collection name
- request timing
- retrieval result counts
- generation failures
- Ollama connectivity failures
- index rebuild events

Useful metrics later:

- request latency
- retrieval latency
- generation latency
- average prompt size
- average number of retrieved chunks
- Ollama timeout rate
- error rate by endpoint

## Failure Modes to Plan For
The first production deployment should explicitly handle:

- Ollama not running
- model missing on the server
- vector store missing or corrupted
- embedding model mismatch between index build and query time
- long prompts exceeding context limits
- server restarts while rebuild jobs are running
- partial artifact deployments

The application should fail clearly when any of these happen. Silent fallback behavior will make debugging harder.

## Deployment Checklist
Before first production rollout:

- decide whether ingestion happens on the server or outside it
- pin the production Ollama model tag
- make generation config environment-driven
- preload the embedding model during application startup
- verify all writable directories exist and persist across restarts
- verify the vector store is present on the server
- verify the required embedding model is available
- verify Ollama is running and the model is already pulled
- verify logs are accessible
- verify the app is reachable only through the intended endpoint

## Recommended Rollout Sequence
Use this sequence when you are ready to productionize.

1. Implement the generation adapter and configuration layer locally.
2. Add a single end-to-end `ask` command or API path.
3. Test the full local flow against Ollama.
4. Decide whether artifacts are built locally, in CI, or on the server.
5. Provision the server directories and service user.
6. Install Python dependencies and Ollama on the server.
7. Pull the pinned production model on the server.
8. Copy or build the retrieval artifacts on the server.
9. Start the application behind a service manager.
10. Add a reverse proxy and TLS if external access is needed.
11. Run smoke tests against a real query.
12. Document the rebuild and rollback procedure.

## Rollback Strategy
Define rollback before the first live deployment.

Recommended rollback targets:

- previous application code revision
- previous vector-store artifact set
- previous known-good Ollama model tag if you change models

If artifacts are shipped separately, version them so you can restore a known-good state quickly.

## Recommended Next Engineering Steps in This Repo
To make the repository production-ready, the next code changes should be:

1. add a `.env.example`
2. add a long-lived API or app process that preloads the embedding model at startup
3. add deployment scripts or service examples once the runtime interface is stable
4. add request-level logging and timing around retrieval and generation
5. tighten retrieval quality so fewer irrelevant chunks reach the prompt

## Non-Goals for the First Production Version
Do not overbuild the first server deployment.

Avoid adding these unless there is a real requirement:

- multi-node model serving
- distributed vector databases
- background job orchestration systems
- autoscaling infrastructure
- multiple model backends at once

The first production target should be stable, inspectable, and easy to recover.

## Summary
The clean production path is:

- keep retrieval and generation separated by a small interface
- run the app and Ollama on the same server
- keep data persistent and outside ephemeral runtime state
- make runtime settings environment-driven
- pin model and artifact versions
- expose only the application, not Ollama itself

If you keep those constraints, moving from local development to the server will be operational work, not architecture churn.
