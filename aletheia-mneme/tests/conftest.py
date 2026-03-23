"""
Pytest configuration and shared fixtures.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    """Return a simple MagicMock that stands in for a SQLAlchemy Session."""
    return MagicMock()


@pytest.fixture
def mock_agent():
    """Return a minimal mock Agent."""
    agent = MagicMock()
    agent.id = "00000000-0000-0000-0000-000000000001"
    agent.name = "test-agent"
    agent.is_active = True
    agent.subscription = None
    return agent
