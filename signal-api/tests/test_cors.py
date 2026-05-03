"""CORS origins이 환경변수로 주입되는지 확인.

importlib.reload로 main 모듈을 재실행해 새 미들웨어를 강제 재구성한다.
"""
from importlib import reload

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_with_origins(monkeypatch):
    monkeypatch.setenv(
        "SIGNAL_API_CORS_ORIGINS",
        "https://signal.example.com,http://localhost:3000",
    )
    import app.main as main_module
    reload(main_module)
    yield main_module.app
    # cleanup: env unset 후 reload하여 다른 테스트에 영향 없도록 함
    monkeypatch.delenv("SIGNAL_API_CORS_ORIGINS", raising=False)
    reload(main_module)


async def test_cors_origins_from_env(app_with_origins):
    transport = ASGITransport(app=app_with_origins)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.options(
            "/api/health",
            headers={
                "Origin": "https://signal.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("access-control-allow-origin") == "https://signal.example.com"


async def test_cors_default_allows_localhost_3000():
    """env 미설정 시 localhost:3000이 fallback으로 허용된다."""
    import app.main as main_module
    reload(main_module)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
