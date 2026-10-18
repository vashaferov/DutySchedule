"""
Ошибочные сценарии: неверная авторизация и запрещённые действия.

PIN и changer из query больше нигде не читаются — регрессия на утечку
PIN в access-логи nginx (инцидент 17.10.2026).
"""
import pytest
from app import crud, schemas


def test_toggle_duty_without_token(client, db, make_user):
    make_user("duty_user_no_token_error")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "01.01.2030", "user_name": "duty_user_no_token_error", "value": True},
    )

    assert response.status_code == 401
    assert "Требуется вход" in response.json()["detail"]


def test_toggle_duty_with_broken_token(client, db, make_user):
    make_user("duty_user_broken")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "01.01.2030", "user_name": "duty_user_broken", "value": True},
        headers={"Authorization": "Bearer garbage"},
    )

    assert response.status_code == 401


def test_toggle_duty_unknown_user_token(client, db, auth_headers):
    """Токен подписан, но пользователя в базе нет (например, его удалили)."""
    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "01.01.2030", "user_name": "nonexistent", "value": True},
        headers=auth_headers("nonexistent"),
    )

    assert response.status_code == 401
    assert "не найден" in response.json()["detail"]


def test_toggle_duty_query_pin_is_ignored(client, db, make_user):
    """Регрессия: pin в query больше не даёт прав."""
    make_user("duty_user_query_pin")

    response = client.post(
        "/api/duty/toggle?changer=duty_user_query_pin&pin=1234",
        json={"date_str": "01.01.2030", "user_name": "duty_user_query_pin", "value": True},
    )

    assert response.status_code == 401


def test_create_song_unauthorized(client, db, auth_headers, make_user):
    make_user("song_user")

    assert client.post("/api/songs/", json={"name": "Test", "text": "Lyrics"}).status_code == 401

    response = client.post(
        "/api/songs/",
        json={"name": "Test", "text": "Lyrics"},
        headers=auth_headers("song_user"),
    )
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_delete_song_unauthorized(client, db, auth_headers, make_user, make_admin):
    make_user("delete_song_user")
    make_admin("admin_song")
    client.post(
        "/api/songs/",
        json={"name": "TestSong", "text": "Lyrics"},
        headers=auth_headers("admin_song"),
    )

    response = client.delete("/api/songs/TestSong", headers=auth_headers("delete_song_user"))

    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_update_missing_song_returns_error(client, db, auth_headers, make_admin):
    make_admin("admin_song_missing")

    response = client.put(
        "/api/songs/Нет такой песни",
        json={"text": "New"},
        headers=auth_headers("admin_song_missing"),
    )

    assert response.status_code == 400
