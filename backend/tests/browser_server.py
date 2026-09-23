"""Isolated browser-test API; never makes paid requests."""
from backend.app.baseline import BaselineProvider
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.memory_storage import MemoryStore

app = create_app(Settings(_env_file=None, openai_api_key="test-only"),
                 provider_factory=lambda mode: BaselineProvider(), store=MemoryStore())

@app.get("/api/test-mode")
def test_mode():
    return {"isolated_browser_test": True}
