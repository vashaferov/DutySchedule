import pytest
from app import crud, schemas

def test_verify_pin(client, db):
    # Создаём тестового пользователя
    user = schemas.UserCreate(name="test_user", pin="1234")
    crud.create_user(db, user)
    
    response = client.get(f"/api/auth/verifyPin?name=test_user&pin=1234")
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_verify_pin_wrong(client, db):
    user = schemas.UserCreate(name="test_user2", pin="1234")
    crud.create_user(db, user)
    
    response = client.get(f"/api/auth/verifyPin?name=test_user2&pin=9999")
    assert response.status_code == 200
    assert response.json()["success"] is False

def test_get_user_names(client, db):
    user1 = schemas.UserCreate(name="alpha", pin="1111")
    user2 = schemas.UserCreate(name="beta", pin="2222")
    crud.create_user(db, user1)
    crud.create_user(db, user2)
    
    response = client.get("/api/auth/getUserNames")
    assert response.status_code == 200
    names = response.json()["names"]
    assert "alpha" in names
    assert "beta" in names