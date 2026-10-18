import pytest
from app import crud, schemas

def test_update_repertoire(client, db):
    admin = schemas.UserCreate(name="rep_admin", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "rep_admin")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    song_resp = client.post(
        "/api/songs/?changer=rep_admin&pin=1234",
        json={"name": "Rep Song", "text": "Lyrics"}
    )
    assert song_resp.status_code == 200

    payload = {"songs": ["Rep Song"]}
    response = client.put(
        "/api/repertoire/01.01.2030?changer=rep_admin&pin=1234",
        json=payload
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    get_resp = client.get("/api/repertoire/")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "01.01.2030" in data
    assert len(data["01.01.2030"]["songs"]) == 1
    assert data["01.01.2030"]["songs"][0]["name"] == "Rep Song"

def test_update_repertoire_unauthorized(client, db):
    user = schemas.UserCreate(name="rep_user", pin="1234")
    crud.create_user(db, user)
    payload = {"songs": []}
    response = client.put(
        "/api/repertoire/01.01.2030?changer=rep_user&pin=1234",
        json=payload
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]

def test_delete_song_from_repertoire(client, db):
    admin = schemas.UserCreate(name="rep_admin2", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "rep_admin2")
    user.role = "admin"
    db.commit()

    # Создаём песню и добавляем в репертуар
    client.post("/api/songs/?changer=rep_admin2&pin=1234", json={"name": "Delete Song", "text": "Lyrics"})
    client.put("/api/repertoire/02.01.2030?changer=rep_admin2&pin=1234", json={"songs": ["Delete Song"]})

    # Удаляем песню из даты
    response = client.delete(
        "/api/repertoire/02.01.2030/Delete Song?changer=rep_admin2&pin=1234"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Проверяем, что песня удалена
    get_resp = client.get("/api/repertoire/")
    data = get_resp.json()
    assert "02.01.2030" in data
    assert len(data["02.01.2030"]["songs"]) == 0

def test_delete_song_from_repertoire_not_found(client, db):
    admin = schemas.UserCreate(name="rep_admin3", pin="1234")
    crud.create_user(db, admin)
    user = crud.get_user_by_name(db, "rep_admin3")
    user.role = "admin"
    db.commit()
    db.refresh(user)

    client.post("/api/songs/?changer=rep_admin3&pin=1234", json={"name": "Existing Song", "text": "Lyrics"})
    client.put("/api/repertoire/01.01.2030?changer=rep_admin3&pin=1234", json={"songs": ["Existing Song"]})

    response = client.delete(
        "/api/repertoire/01.01.2030/NonExistent?changer=rep_admin3&pin=1234"
    )
    assert response.status_code == 404
    assert "Song not found in repertoire" in response.json()["detail"]
