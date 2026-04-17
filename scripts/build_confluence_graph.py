"""Build the persisted document/chunk graph artifact for Confluence content."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cortex_rag.cli import main as cli_main


def main() -> None:
    cli_main(["build-graph", *sys.argv[1:]])


if __name__ == "__main__":
    main()
