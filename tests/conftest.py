import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MATNYAB_ENGINE", "stub")

import pytest  # noqa: E402


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point MATNYAB_DATA_DIR at a fresh temporary folder."""
    path = tmp_path / "data"
    monkeypatch.setenv("MATNYAB_DATA_DIR", str(path))
    return path
