import pytest
from app import crud, schemas

def test_create_song(client, db):
    admin = schemas.UserCreate(name="admin", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "admin")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    response = client.post(
        "/api/songs/?changer=admin&pin=1234",
        json={"name": "Test Song", "text": "Lyrics"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Song"
    assert data["text"] == "Lyrics"

def test_get_songs(client, db):
    response = client.get("/api/songs/")
    assert response.status_code == 200

def test_update_song_text(client, db):
    admin = schemas.UserCreate(name="song_admin2", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "song_admin2")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    client.post("/api/songs/?changer=song_admin2&pin=1234", json={"name": "Update Song", "text": "Old"})

    response = client.put(
        "/api/songs/Update Song?new_text=New&changer=song_admin2&pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["song"]["text"] == "New"

def test_update_song_text_unauthorized(client, db):
    from app import crud, schemas
    user = schemas.UserCreate(name="song_user2", pin="1234")
    crud.create_user(db, user)
    response = client.put(
        "/api/songs/Any?new_text=New&changer=song_user2&pin=1234"
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]

def test_delete_song(client, db):
    admin = schemas.UserCreate(name="song_admin3", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "song_admin3")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    client.post("/api/songs/?changer=song_admin3&pin=1234", json={"name": "ToDelete", "text": "Lyrics"})

    response = client.delete("/api/songs/ToDelete?changer=song_admin3&pin=1234")
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_delete_song_unauthorized(client, db):
    from app import crud, schemas
    user = schemas.UserCreate(name="song_user3", pin="1234")
    crud.create_user(db, user)
    response = client.delete("/api/songs/Some?changer=song_user3&pin=1234")
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]