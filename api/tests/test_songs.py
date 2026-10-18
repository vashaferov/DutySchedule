"""
Песни: правки только администратором, текст — в теле запроса (в query он
упирался в лимит длины URL), авторизация — токеном.
"""
import pytest
from app import crud, schemas


def test_create_song(client, db, auth_headers, make_admin):
    make_admin("admin")
    headers = auth_headers("admin")

    response = client.post("/api/songs/", json={"name": "Test Song", "text": "Lyrics"}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Song"
    assert data["text"] == "Lyrics"


def test_create_song_without_token(client, db):
    response = client.post("/api/songs/", json={"name": "No Token", "text": "Lyrics"})

    assert response.status_code == 401


def test_get_songs(client):
    response = client.get("/api/songs/")

    assert response.status_code == 200


def test_update_song_text(client, db, auth_headers, make_admin):
    make_admin("song_admin2")
    headers = auth_headers("song_admin2")
    client.post("/api/songs/", json={"name": "Update Song", "text": "Old"}, headers=headers)

    response = client.put("/api/songs/Update Song", json={"text": "New"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["song"]["text"] == "New"


def test_update_song_text_accepts_long_text(client, db, auth_headers, make_admin):
    """Полный текст песни не влезает в URL — поэтому он в теле запроса."""
    make_admin("song_admin_long")
    headers = auth_headers("song_admin_long")
    client.post("/api/songs/", json={"name": "Long Song", "text": "Old"}, headers=headers)
    long_text = "Куплет\n" * 2000

    response = client.put("/api/songs/Long Song", json={"text": long_text}, headers=headers)

    assert response.status_code == 200
    assert response.json()["song"]["text"] == long_text


def test_update_song_text_not_accepted_in_query(client, db, auth_headers, make_admin):
    """Регрессия: текст и PIN больше не едут в query string."""
    make_admin("song_admin_query")
    headers = auth_headers("song_admin_query")
    client.post("/api/songs/", json={"name": "Query Song", "text": "Old"}, headers=headers)

    response = client.put("/api/songs/Query Song?new_text=New&changer=song_admin_query&pin=1234", headers=headers)

    assert response.status_code == 422


def test_update_song_text_unauthorized(client, db, auth_headers, make_user):
    make_user("song_user2")

    assert client.put("/api/songs/Any", json={"text": "New"}).status_code == 401

    response = client.put("/api/songs/Any", json={"text": "New"}, headers=auth_headers("song_user2"))
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_delete_song(client, db, auth_headers, make_admin):
    make_admin("song_admin3")
    headers = auth_headers("song_admin3")
    client.post("/api/songs/", json={"name": "ToDelete", "text": "Lyrics"}, headers=headers)

    response = client.delete("/api/songs/ToDelete", headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_delete_song_unauthorized(client, db, auth_headers, make_user):
    make_user("song_user3")

    assert client.delete("/api/songs/Some").status_code == 401

    response = client.delete("/api/songs/Some", headers=auth_headers("song_user3"))
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]
