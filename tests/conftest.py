import pytest
from src.main import app


@pytest.fixture(autouse=True)
def reset_app_config():
    """
    Autouse fixture to isolate application state between tests.
    Ensures that any modifications to app.state.config are reset
    before and after each test function, providing complete test state isolation.
    """
    app.state.config = None
    yield
    app.state.config = None
