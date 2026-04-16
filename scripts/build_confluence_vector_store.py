"""Build the persistent vector store from embedded Confluence chunks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.config import DEFAULT_VECTOR_COLLECTION, VECTOR_DB_DIR
from cortex_rag.retrieval import build_confluence_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("auto", "chroma", "faiss"),
        default="auto",
        help="Vector store backend. Defaults to Chroma when available, otherwise FAISS.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_VECTOR_COLLECTION,
        help="Persistent collection name to create or replace.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=VECTOR_DB_DIR,
        help="Directory where the vector store files should be persisted.",
    )
    args = parser.parse_args()

    result = build_confluence_vector_store(
        persist_dir=args.output_dir,
        collection_name=args.collection,
        backend=args.backend,
    )

    print(
        f"Built {result.backend} vector store '{result.collection_name}' "
        f"with {result.document_count} chunks at {result.persist_dir}."
    )


if __name__ == "__main__":
    main()
