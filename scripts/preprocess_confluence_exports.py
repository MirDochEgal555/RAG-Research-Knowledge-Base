"""Preprocess Confluence HTML zip exports into Markdown files."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.ingestion.confluence_html import preprocess_confluence_exports


def main() -> None:
    output_paths = preprocess_confluence_exports()
    print(f"Wrote {len(output_paths)} Markdown files.")
    for path in output_paths:
        print(path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
