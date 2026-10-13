from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_scratch_directory():
    """Ensure standard scratch directory exists for isolated testing."""
    root = Path("/tmp/Authy-to-1Password_Local")
    root.mkdir(parents=True, exist_ok=True)
    yield
