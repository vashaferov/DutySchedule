import pytest
from app import crud, schemas

def test_toggle_duty_invalid_user(client):
    payload = {
        "date_str": "01.01.2030",
        "user_name": "nonexistent",
        "value": True,
        "changer": "nonexistent",
        "pin": "1234"
    }
    response = client.post("/api/duty/toggle", json=payload)
    assert response.status_code == 401  # или 400, смотря как обработано
    # В вашем коде это может быть 401, если PIN неверный

def test_toggle_duty_wrong_pin(client, db):
    user = schemas.UserCreate(name="duty_user_pin", pin="1234")
    crud.create_user(db, user)
    payload = {
        "date_str": "01.01.2030",
        "user_name": "duty_user_pin",
        "value": True,
        "changer": "duty_user_pin",
        "pin": "wrong"
    }
    response = client.post("/api/duty/toggle", json=payload)
    assert response.status_code == 401
    assert "Invalid PIN" in response.json()["detail"]

def test_create_song_unauthorized(client, db):
    user = schemas.UserCreate(name="song_user", pin="1234")
    crud.create_user(db, user)

    response = client.post(
        "/api/songs/?changer=song_user&pin=1234",
        json={"name": "Test", "text": "Lyrics"}
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]

def test_delete_song_unauthorized(client, db):
    user = schemas.UserCreate(name="delete_song_user", pin="1234")
    crud.create_user(db, user)
    # Создаём песню как админ (нужно создать админа)
    admin = schemas.UserCreate(name="admin_song", pin="1234")
    crud.create_user(db, admin)
    admin_user = crud.get_user_by_name(db, "admin_song")
    admin_user.role = "admin"
    db.commit()
    client.post("/api/songs/?changer=admin_song&pin=1234", json={"name": "TestSong", "text": "Lyrics"})

    response = client.delete(
        "/api/songs/TestSong?changer=delete_song_user&pin=1234"
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]