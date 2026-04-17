"""Tests for the legacy graph-build script wrapper."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts import build_confluence_graph


def test_script_main_delegates_to_cli(monkeypatch) -> None:
    captured: list[str] = []

    monkeypatch.setattr(sys, "argv", ["build_confluence_graph.py", "--similarity-top-k", "4"])
    monkeypatch.setattr(build_confluence_graph, "cli_main", lambda argv: captured.extend(argv))

    build_confluence_graph.main()

    assert captured == ["build-graph", "--similarity-top-k", "4"]
