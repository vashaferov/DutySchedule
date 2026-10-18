"""
Управление пользователями: всё требует токена администратора, PIN и роль
передаются в теле запроса, а не в query string.
"""
import pytest
from app import crud, schemas


def test_create_user(client, db, auth_headers, make_admin):
    make_admin("admin_user")

    response = client.post(
        "/api/users/",
        json={"name": "new_user", "pin": "5678", "role": "user"},
        headers=auth_headers("admin_user"),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["user"] == {"name": "new_user", "role": "user"}


def test_create_user_with_admin_role_grants_access(client, db, auth_headers, make_admin):
    make_admin("admin_user_role")

    response = client.post(
        "/api/users/",
        json={"name": "fresh_admin", "pin": "5678", "role": "admin"},
        headers=auth_headers("admin_user_role"),
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert client.get("/api/users/", headers=auth_headers("fresh_admin")).status_code == 200


def test_create_user_already_exists(client, db, auth_headers, make_admin):
    make_admin("admin_user2")
    crud.create_user(db, schemas.UserCreate(name="existing_user", pin="5678"))

    response = client.post(
        "/api/users/",
        json={"name": "existing_user", "pin": "5678"},
        headers=auth_headers("admin_user2"),
    )

    assert response.status_code == 400
    assert "User already exists" in response.json()["detail"]


def test_create_user_rejects_invalid_role(client, db, auth_headers, make_admin):
    make_admin("admin_user_bad_role")

    response = client.post(
        "/api/users/",
        json={"name": "weird_user", "pin": "5678", "role": "superuser"},
        headers=auth_headers("admin_user_bad_role"),
    )

    assert response.status_code == 400
    assert "Invalid role" in response.json()["detail"]


def test_create_user_pin_not_accepted_in_query(client, db, auth_headers, make_admin):
    """Регрессия: PIN в query больше не проходит — тело запроса обязательно."""
    make_admin("admin_user_query")

    response = client.post(
        "/api/users/?name=query_user&pin=5678",
        headers=auth_headers("admin_user_query"),
    )

    assert response.status_code == 422


def test_delete_user(client, db, auth_headers, make_admin):
    make_admin("admin_user3")
    crud.create_user(db, schemas.UserCreate(name="to_delete", pin="5678"))

    response = client.delete("/api/users/to_delete", headers=auth_headers("admin_user3"))

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert crud.get_user_by_name(db, "to_delete") is None


def test_change_user_role(client, db, auth_headers, make_admin):
    make_admin("admin_user4")
    crud.create_user(db, schemas.UserCreate(name="role_user", pin="5678"))

    response = client.put(
        "/api/users/role_user/role",
        json={"role": "admin"},
        headers=auth_headers("admin_user4"),
    )

    assert response.status_code == 200
    assert response.json()["user"] == {"name": "role_user", "role": "admin"}
    assert client.get("/api/users/", headers=auth_headers("role_user")).status_code == 200


def test_change_user_role_rejects_unknown_value(client, db, auth_headers, make_admin):
    make_admin("admin_user_role_bad")
    crud.create_user(db, schemas.UserCreate(name="role_user_bad", pin="5678"))

    response = client.put(
        "/api/users/role_user_bad/role",
        json={"role": "root"},
        headers=auth_headers("admin_user_role_bad"),
    )

    assert response.status_code == 400
    assert "Invalid role" in response.json()["detail"]


def test_change_user_pin(client, db, auth_headers, make_admin):
    make_admin("admin_user5")
    crud.create_user(db, schemas.UserCreate(name="pin_user", pin="5678"))

    response = client.put(
        "/api/users/pin_user/pin",
        json={"new_pin": "9999"},
        headers=auth_headers("admin_user5"),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    # Новый PIN должен работать при входе, старый — нет.
    assert client.post("/api/auth/login", json={"name": "pin_user", "pin": "9999"}).status_code == 200
    assert client.post("/api/auth/login", json={"name": "pin_user", "pin": "5678"}).status_code == 401


def test_get_users(client, db, auth_headers, make_admin):
    make_admin("admin_user_list")
    crud.create_user(db, schemas.UserCreate(name="user_a", pin="1111"))
    crud.create_user(db, schemas.UserCreate(name="user_b", pin="2222"))

    response = client.get("/api/users/", headers=auth_headers("admin_user_list"))

    assert response.status_code == 200
    names = [u["name"] for u in response.json()]
    assert "user_a" in names
    assert "user_b" in names
    assert "admin_user_list" in names


def test_get_users_unauthorized(client, db, auth_headers):
    crud.create_user(db, schemas.UserCreate(name="user_unauth", pin="1234"))

    assert client.get("/api/users/").status_code == 401
    response = client.get("/api/users/", headers=auth_headers("user_unauth"))
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]
