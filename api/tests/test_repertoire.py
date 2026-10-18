"""
Репертуар: чтение публичное, правки — администратором по токену.
"""
import pytest
from app import crud, schemas


def test_update_repertoire(client, db, auth_headers, make_admin):
    make_admin("rep_admin")
    headers = auth_headers("rep_admin")

    song_resp = client.post("/api/songs/", json={"name": "Rep Song", "text": "Lyrics"}, headers=headers)
    assert song_resp.status_code == 200

    response = client.put("/api/repertoire/01.01.2030", json={"songs": ["Rep Song"]}, headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is True

    data = client.get("/api/repertoire/").json()
    assert "01.01.2030" in data
    assert len(data["01.01.2030"]["songs"]) == 1
    assert data["01.01.2030"]["songs"][0]["name"] == "Rep Song"


def test_update_repertoire_unauthorized(client, db, auth_headers, make_user):
    make_user("rep_user")

    assert client.put("/api/repertoire/01.01.2030", json={"songs": []}).status_code == 401

    response = client.put(
        "/api/repertoire/01.01.2030",
        json={"songs": []},
        headers=auth_headers("rep_user"),
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_delete_song_from_repertoire(client, db, auth_headers, make_admin):
    make_admin("rep_admin2")
    headers = auth_headers("rep_admin2")

    client.post("/api/songs/", json={"name": "Delete Song", "text": "Lyrics"}, headers=headers)
    client.put("/api/repertoire/02.01.2030", json={"songs": ["Delete Song"]}, headers=headers)

    response = client.delete("/api/repertoire/02.01.2030/Delete Song", headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is True

    data = client.get("/api/repertoire/").json()
    assert "02.01.2030" in data
    assert len(data["02.01.2030"]["songs"]) == 0


def test_delete_song_from_repertoire_requires_admin(client, db, auth_headers, make_user, make_admin):
    make_user("rep_user_del")
    make_admin("rep_admin_del")
    admin_headers = auth_headers("rep_admin_del")
    client.post("/api/songs/", json={"name": "Guarded Song", "text": "Lyrics"}, headers=admin_headers)
    client.put("/api/repertoire/05.01.2030", json={"songs": ["Guarded Song"]}, headers=admin_headers)

    response = client.delete("/api/repertoire/05.01.2030/Guarded Song", headers=auth_headers("rep_user_del"))

    assert response.status_code == 403


def test_delete_song_from_repertoire_not_found(client, db, auth_headers, make_admin):
    make_admin("rep_admin3")
    headers = auth_headers("rep_admin3")

    client.post("/api/songs/", json={"name": "Existing Song", "text": "Lyrics"}, headers=headers)
    client.put("/api/repertoire/01.01.2030", json={"songs": ["Existing Song"]}, headers=headers)

    response = client.delete("/api/repertoire/01.01.2030/NonExistent", headers=headers)

    assert response.status_code == 404
    assert "Song not found in repertoire" in response.json()["detail"]
