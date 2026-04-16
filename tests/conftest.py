"""Pytest fixtures for local test execution."""

from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_TMP_ROOT = PROJECT_ROOT / "scratch_pytest"


@pytest.fixture
def tmp_path() -> Path:
    """Provide a repo-local temporary directory without using pytest's tmpdir plugin."""

    LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = LOCAL_TMP_ROOT / f"test-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    yield path
    shutil.rmtree(path, ignore_errors=True)
