import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Reviews, rules, and profile versions go to a temporary folder, never the real .draftvoice/."""
    monkeypatch.setenv("DRAFTVOICE_HOME", str(tmp_path / "home"))
