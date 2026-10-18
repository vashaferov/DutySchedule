import pytest
from unittest.mock import AsyncMock, patch
from app import crud, schemas

@pytest.fixture
def admin_user(db):
    admin = schemas.UserCreate(name="sync_admin_test", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "sync_admin_test")
    user.role = "admin"
    db.commit()
    db.refresh(user)  # <-- ВАЖНО: обновляем объект
    return user

@pytest.fixture
def regular_user(db):
    user = schemas.UserCreate(name="regular_user_test", pin="1234")
    crud.create_user(db, user)
    return user

def test_run_sync(client, admin_user):
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(
            status_code=200,
            json=lambda: {"success": True, "message": "Sync completed"}
        ))
        mock_client_class.return_value.__aenter__.return_value = mock_client

        response = client.post(
            "/api/sync/run?changer=sync_admin_test&pin=1234"
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["message"] == "Sync completed"

def test_run_sync_service_unavailable(client, admin_user):
    with patch('httpx.AsyncClient') as mock_client:
        from httpx import ConnectError
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = ConnectError("Connection refused")
        mock_client.return_value.__aenter__.return_value = mock_instance

        response = client.post(
            "/api/sync/run?changer=sync_admin_test&pin=1234"
        )
        assert response.status_code == 503
        assert "Sync service unavailable" in response.json()["detail"]

def test_run_sync_unauthorized(client, regular_user):
    response = client.post(
        "/api/sync/run?changer=regular_user_test&pin=1234"
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]

def test_sync_history(client, admin_user, db):
    from app.models import SyncHistory
    history = SyncHistory(
        triggered_by="sync_admin_test",
        changes_summary="Test history",
        status="success"
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    response = client.get(
        "/api/sync/history?admin_name=sync_admin_test&admin_pin=1234&limit=10"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["triggered_by"] == "sync_admin_test"
    assert data[0]["status"] == "success"