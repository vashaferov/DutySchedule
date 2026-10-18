import pytest
from app import crud, schemas

def test_create_user(client, db):
    admin = schemas.UserCreate(name="admin_user", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    response = client.post(
        "/api/users/?name=new_user&pin=5678&admin_name=admin_user&admin_pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["user"]["name"] == "new_user"

def test_create_user_already_exists(client, db):
    admin = schemas.UserCreate(name="admin_user2", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user2")
    user.role = "admin"
    db.commit()

    # Создаём пользователя
    client.post("/api/users/?name=existing_user&pin=5678&admin_name=admin_user2&admin_pin=1234")
    # Пытаемся создать повторно
    response = client.post("/api/users/?name=existing_user&pin=5678&admin_name=admin_user2&admin_pin=1234")
    assert response.status_code == 400
    assert "User already exists" in response.json()["detail"]

def test_delete_user(client, db):
    admin = schemas.UserCreate(name="admin_user3", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user3")
    user.role = "admin"
    db.commit()

    # Создаём пользователя
    client.post("/api/users/?name=to_delete&pin=5678&admin_name=admin_user3&admin_pin=1234")
    # Удаляем
    response = client.delete(
        "/api/users/to_delete?admin_name=admin_user3&admin_pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_change_user_role(client, db):
    admin = schemas.UserCreate(name="admin_user4", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user4")
    user.role = "admin"
    db.commit()

    client.post("/api/users/?name=role_user&pin=5678&admin_name=admin_user4&admin_pin=1234")
    response = client.put(
        "/api/users/role_user/role?role=admin&admin_name=admin_user4&admin_pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_change_user_pin(client, db):
    admin = schemas.UserCreate(name="admin_user5", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user5")
    user.role = "admin"
    db.commit()

    client.post("/api/users/?name=pin_user&pin=5678&admin_name=admin_user5&admin_pin=1234")
    response = client.put(
        "/api/users/pin_user/pin?new_pin=9999&admin_name=admin_user5&admin_pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_get_users(client, db):
    admin = schemas.UserCreate(name="admin_user_list", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin_user_list")
    user.role = "admin"
    db.commit()

    # Создаём нескольких пользователей
    client.post("/api/users/?name=user_a&pin=1111&admin_name=admin_user_list&admin_pin=1234")
    client.post("/api/users/?name=user_b&pin=2222&admin_name=admin_user_list&admin_pin=1234")

    response = client.get("/api/users/?admin_name=admin_user_list&admin_pin=1234")
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    names = [u["name"] for u in users]
    assert "user_a" in names
    assert "user_b" in names
    assert "admin_user_list" in names

def test_get_users_unauthorized(client, db):
    user = schemas.UserCreate(name="user_unauth", pin="1234")
    crud.create_user(db, user)
    response = client.get("/api/users/?admin_name=user_unauth&admin_pin=1234")
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]