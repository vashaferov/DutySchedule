"""
Авторизация: PIN меняется на токен.

PIN уходит только в POST /api/auth/login — раньше он приезжал в query почти
каждой ручки и оседал в access-логах nginx (инцидент 17.10.2026).
"""
import pytest
from app import crud, schemas


def _make(db, name, pin="1234", role="user"):
    crud.create_user(db, schemas.UserCreate(name=name, pin=pin))
    if role != "user":
        crud.update_user_role(db, name, role)
    return name


def test_login_returns_token(client, db):
    _make(db, "login_user", pin="1234")

    response = client.post("/api/auth/login", json={"name": "login_user", "pin": "1234"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["role"] == "user"
    assert body["token"]


def test_login_wrong_pin(client, db):
    _make(db, "login_user2", pin="1234")

    response = client.post("/api/auth/login", json={"name": "login_user2", "pin": "9999"})

    assert response.status_code == 401
    assert "token" not in response.json()


def test_login_unknown_user(client, db):
    response = client.post("/api/auth/login", json={"name": "nobody", "pin": "1234"})

    assert response.status_code == 401


def test_login_pin_is_not_accepted_in_query(client, db):
    """Регрессия: PIN в query больше не пускает — иначе он снова попадёт в логи."""
    _make(db, "login_user3", pin="1234")

    response = client.post("/api/auth/login?name=login_user3&pin=1234")

    assert response.status_code == 422  # тело запроса обязательно


def test_me_returns_user(client, db, auth_headers):
    _make(db, "me_user")

    response = client.get("/api/auth/me", headers=auth_headers("me_user"))

    assert response.status_code == 200
    assert response.json() == {"name": "me_user", "role": "user"}


def test_me_without_token(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert "Требуется вход" in response.json()["detail"]


def test_me_with_broken_token(client, db):
    _make(db, "me_user2")

    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401


def test_me_with_expired_token(client, db):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.security import ALGORITHM, SECRET_KEY

    _make(db, "expired_user")
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "expired_user",
            "role": "user",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_token_of_deleted_user_stops_working(client, db, auth_headers, make_admin):
    """Токен не должен переживать удаление пользователя."""
    make_admin("cleanup_admin")
    _make(db, "doomed_user")
    headers = auth_headers("doomed_user")
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    client.delete("/api/users/doomed_user", headers=auth_headers("cleanup_admin"))

    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_demoted_admin_loses_rights_immediately(client, db, auth_headers, make_admin):
    """Роль берётся из базы, а не из токена: разжалование действует сразу."""
    make_admin("boss_user")
    make_admin("victim_user")
    victim_headers = auth_headers("victim_user", role="admin")
    assert client.get("/api/users/", headers=victim_headers).status_code == 200

    crud.update_user_role(db, "victim_user", "user")

    assert client.get("/api/users/", headers=victim_headers).status_code == 403


def test_get_user_names_is_public(client, db):
    _make(db, "alpha", pin="1111")
    _make(db, "beta", pin="2222")

    response = client.get("/api/auth/getUserNames")

    assert response.status_code == 200
    names = response.json()["names"]
    assert "alpha" in names
    assert "beta" in names


def test_get_users_requires_admin(client, db, auth_headers, make_admin):
    make_admin("users_admin")
    _make(db, "plain_user")

    assert client.get("/api/users/").status_code == 401
    assert client.get("/api/users/", headers=auth_headers("plain_user")).status_code == 403

    response = client.get("/api/users/", headers=auth_headers("users_admin"))
    assert response.status_code == 200
    assert any(u["name"] == "plain_user" for u in response.json())


def test_legacy_verify_pin_endpoint_removed(client, db):
    """Ручка, через которую PIN уезжал в query, удалена."""
    response = client.get("/api/auth/verifyPin?name=test_user&pin=1234")

    assert response.status_code == 404


def test_query_pin_does_not_authenticate(client, db):
    """Регрессия на исходную утечку: admin_pin в query больше ничего не даёт."""
    _make(db, "query_admin", role="admin")

    response = client.get("/api/users/?admin_name=query_admin&admin_pin=1234")

    assert response.status_code == 401
