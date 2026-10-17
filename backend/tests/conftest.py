import pytest


@pytest.fixture(autouse=True)
def local_decision_engine_for_tests(monkeypatch):
    """Keep tests offline unless a test explicitly exercises the Jev adapter."""
    monkeypatch.setenv("DECISION_ENGINE", "local")
