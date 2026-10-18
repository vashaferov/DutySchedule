"""
Синхронизация с Google Sheets и история синхронизаций.

Запуск синхронизации — только администратором; в sync-сервис уходит тот же
Bearer-токен (PIN для этого больше не нужен).
"""
import pytest
from unittest.mock import AsyncMock, patch
from app import crud, schemas


def test_run_sync(client, auth_headers, make_admin):
    make_admin("sync_admin_test")
    token_headers = auth_headers("sync_admin_test")

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(
            status_code=200,
            json=lambda: {"success": True, "message": "Sync completed"},
        ))
        mock_client_class.return_value.__aenter__.return_value = mock_client

        response = client.post("/api/sync/run", headers=token_headers)

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["message"] == "Sync completed"

        # Токен вызывающего уходит в sync-сервис как есть — тот проверит подпись сам.
        forwarded = mock_client.post.call_args.kwargs["headers"]["Authorization"]
        assert forwarded == token_headers["Authorization"]


def test_run_sync_service_unavailable(client, auth_headers, make_admin):
    make_admin("sync_admin_down")

    with patch("httpx.AsyncClient") as mock_client:
        from httpx import ConnectError
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = ConnectError("Connection refused")
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post("/api/sync/run", headers=auth_headers("sync_admin_down"))

        assert response.status_code == 503
        assert "Sync service unavailable" in response.json()["detail"]


def test_run_sync_requires_token(client, db, make_user):
    make_user("sync_user_no_token")

    response = client.post("/api/sync/run")

    assert response.status_code == 401


def test_run_sync_unauthorized(client, db, auth_headers, make_user):
    make_user("regular_user_test")

    response = client.post("/api/sync/run", headers=auth_headers("regular_user_test"))

    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_run_sync_query_pin_no_longer_works(client, db, make_user, make_admin):
    """Регрессия: changer/pin в query больше не запускают синхронизацию."""
    make_admin("sync_admin_query_pin")

    response = client.post("/api/sync/run?changer=sync_admin_query_pin&pin=1234")

    assert response.status_code == 401


def test_sync_history(client, auth_headers, make_admin, db):
    from app.models import SyncHistory

    make_admin("sync_admin_test")
    db.add(SyncHistory(
        triggered_by="sync_admin_test",
        changes_summary="Test history",
        status="success",
    ))
    db.commit()

    response = client.get("/api/sync/history?limit=10", headers=auth_headers("sync_admin_test"))

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["triggered_by"] == "sync_admin_test"
    assert data[0]["status"] == "success"


def test_sync_history_requires_admin(client, db, auth_headers, make_user):
    make_user("history_plain_user")

    assert client.get("/api/sync/history").status_code == 401

    response = client.get("/api/sync/history", headers=auth_headers("history_plain_user"))
    assert response.status_code == 403


def test_sync_history_timestamps_are_utc(client, auth_headers, make_admin, db):
    """Время отдаётся с явным смещением UTC, чтобы клиент перевёл его в пояс пользователя."""
    from datetime import datetime, timedelta
    from app.models import SyncHistory

    make_admin("sync_admin_test")
    db.add(SyncHistory(
        triggered_by="sync_admin_test",
        changes_summary="Проверка часового пояса",
        status="success",
    ))
    db.commit()

    response = client.get("/api/sync/history?limit=10", headers=auth_headers("sync_admin_test"))
    assert response.status_code == 200

    started = response.json()[0]["started_at"]
    assert started is not None
    assert started.endswith("+00:00"), started

    parsed = datetime.fromisoformat(started)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
