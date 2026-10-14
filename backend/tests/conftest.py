import pytest
from fastapi.testclient import TestClient

from app.core.config import RuntimeConfig
from app.llm.fake import FakeLLMClient
from app.main import create_app

TOKEN = "test-token"
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture
def make_client(tmp_path):
    def _make(fake: FakeLLMClient | None = None, llm_override: str | None = None):
        fake = fake or FakeLLMClient()
        config = RuntimeConfig(
            data_root=tmp_path,
            host="127.0.0.1",
            port=8000,
            llm_base_url_override=llm_override,
            allowed_origins=frozenset({ORIGIN}),
        )
        app = create_app(
            config, token=TOKEN, llm_factory=lambda _s: fake, frontend_dist=tmp_path / "x"
        )
        return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})

    return _make


@pytest.fixture
def client(make_client):
    return make_client()
