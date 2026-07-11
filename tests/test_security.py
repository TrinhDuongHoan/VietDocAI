import pytest
from fastapi import HTTPException

from app.api.security import require_api_key
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_require_api_key_allows_requests_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.delenv("API_KEY", raising=False)

    require_api_key(None)


def test_require_api_key_rejects_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("API_KEY", "secret")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(None)

    assert exc_info.value.status_code == 401


def test_require_api_key_accepts_matching_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("API_KEY", "secret")

    require_api_key("secret")
