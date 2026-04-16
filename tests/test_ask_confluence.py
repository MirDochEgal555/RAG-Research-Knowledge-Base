"""Tests for the end-to-end ask script helpers."""

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


def test_format_duration_uses_two_decimal_places() -> None:
    assert ask_confluence._format_duration(2.3456) == "2.35s"


def test_print_timings_formats_all_stages(capsys) -> None:
    ask_confluence._print_timings(
        embedding_seconds=1.23,
        retrieval_seconds=0.45,
        generation_seconds=6.78,
        total_seconds=8.46,
    )

    assert capsys.readouterr().out.splitlines() == [
        "Timings:",
        "embedding: 1.23s",
        "retrieval: 0.45s",
        "generation: 6.78s",
        "total: 8.46s",
    ]
