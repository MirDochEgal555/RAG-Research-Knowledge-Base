"""Tests for the legacy ask script wrapper."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts import ask_confluence


def test_script_main_delegates_to_cli(monkeypatch) -> None:
    captured: list[str] = []

    monkeypatch.setattr(sys, "argv", ["ask_confluence.py", "What changed?", "--stream"])
    monkeypatch.setattr(ask_confluence, "cli_main", lambda argv: captured.extend(argv))

    ask_confluence.main()

    assert captured == ["ask", "What changed?", "--stream"]
