"""
Дежурства: назначение/снятие, даты, журнал изменений.

Раньше в каждом запросе ехали changer и pin; теперь пользователя определяет
токен, а в журнал изменений попадает имя из токена.
"""
import pytest
from app import crud, schemas


def test_toggle_duty(client, db, auth_headers, make_user):
    make_user("duty_user")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "01.01.2030", "user_name": "duty_user", "value": True},
        headers=auth_headers("duty_user"),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    data = client.get("/api/duty/matrix").json()
    assert "01.01.2030" in data["dates"]
    idx = data["names"].index("duty_user")
    date_idx = data["dates"].index("01.01.2030")
    assert data["matrix"][date_idx][idx] is True


def test_toggle_duty_remove(client, db, auth_headers, make_user):
    make_user("duty_user2")
    headers = auth_headers("duty_user2")

    add = client.post(
        "/api/duty/toggle",
        json={"date_str": "02.01.2030", "user_name": "duty_user2", "value": True},
        headers=headers,
    )
    assert add.status_code == 200

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "02.01.2030", "user_name": "duty_user2", "value": False},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_toggle_duty_requires_token(client, db, make_user):
    make_user("duty_user_no_token")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "01.01.2030", "user_name": "duty_user_no_token", "value": True},
    )

    assert response.status_code == 401


def test_toggle_duty_for_other_user_forbidden(client, db, auth_headers, make_user):
    make_user("duty_user_self")
    make_user("duty_user_other")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "03.01.2030", "user_name": "duty_user_other", "value": True},
        headers=auth_headers("duty_user_self"),
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


def test_toggle_duty_admin_can_change_anyone(client, db, auth_headers, make_user, make_admin):
    make_user("duty_user_target")
    make_admin("duty_admin_any")

    response = client.post(
        "/api/duty/toggle",
        json={"date_str": "04.01.2030", "user_name": "duty_user_target", "value": True},
        headers=auth_headers("duty_admin_any"),
    )

    assert response.status_code == 200

    # В журнал пишется тот, кто авторизован, а не «changer» из тела запроса.
    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "duty_admin_any" and "duty_user_target" in c["text"] for c in changes)


def test_create_date_by_admin(client, db, auth_headers, make_admin):
    make_admin("date_admin")

    resp = client.post(
        "/api/duty/dates",
        json={"date_str": "10.10.2030 (утро 10-12)"},
        headers=auth_headers("date_admin"),
    )

    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2030 (утро 10-12)"
    assert "10.10.2030 (утро 10-12)" in client.get("/api/duty/matrix").json()["dates"]


def test_create_date_normalizes_spaces(client, db, auth_headers, make_admin):
    make_admin("date_admin_norm")

    resp = client.post(
        "/api/duty/dates",
        json={"date_str": "  10.10.2031 (утро   10-12)  "},
        headers=auth_headers("date_admin_norm"),
    )

    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2031 (утро 10-12)"


def test_create_date_requires_admin(client, db, auth_headers, make_user):
    make_user("plain_dates")

    assert client.post(
        "/api/duty/dates",
        json={"date_str": "11.10.2030"},
    ).status_code == 401

    resp = client.post(
        "/api/duty/dates",
        json={"date_str": "11.10.2030"},
        headers=auth_headers("plain_dates"),
    )
    assert resp.status_code == 403


def test_create_date_rejects_bad_format(client, db, auth_headers, make_admin):
    make_admin("date_admin_bad")

    resp = client.post(
        "/api/duty/dates",
        json={"date_str": "10/10/2030"},
        headers=auth_headers("date_admin_bad"),
    )

    assert resp.status_code == 400


def test_create_date_rejects_html_in_note(client, db, auth_headers, make_admin):
    """Примечание к дате — это был вектор stored XSS, HTML туда проходить не должен."""
    make_admin("date_admin_xss")
    headers = auth_headers("date_admin_xss")
    payloads = [
        "10.10.2032 (<img src=x onerror=alert(1)>)",
        '10.10.2032 (" onmouseover="alert(1))',
        "10.10.2032 (<script>alert(1)</script>)",
        "10.10.2032 (а/b)",
        "10.10.2032 (а&б)",
    ]

    for date_str in payloads:
        resp = client.post("/api/duty/dates", json={"date_str": date_str}, headers=headers)
        assert resp.status_code == 400, date_str

    dates = client.get("/api/duty/matrix").json()["dates"]
    assert not any("<" in d or ">" in d for d in dates)


def test_create_date_accepts_safe_note_chars(client, db, auth_headers, make_admin):
    """Обычные примечания (запятые, двоеточия, тире, №) по-прежнему принимаются."""
    make_admin("date_admin_ok_note")

    resp = client.post(
        "/api/duty/dates",
        json={"date_str": " 10.10.2033 (вечер, 18:00-20:00 — по заявке №5) "},
        headers=auth_headers("date_admin_ok_note"),
    )

    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2033 (вечер, 18:00-20:00 — по заявке №5)"


def test_create_date_rejects_duplicate(client, db, auth_headers, make_admin):
    make_admin("date_admin_dup")
    headers = auth_headers("date_admin_dup")

    assert client.post("/api/duty/dates", json={"date_str": "12.10.2030"}, headers=headers).status_code == 200
    assert client.post("/api/duty/dates", json={"date_str": "12.10.2030"}, headers=headers).status_code == 400


def test_toggle_records_change(client, db, auth_headers, make_user):
    make_user("change_user")

    client.post(
        "/api/duty/toggle",
        json={"date_str": "13.10.2030", "user_name": "change_user", "value": True},
        headers=auth_headers("change_user"),
    )

    db.rollback()  # берём свежие данные из БД
    changes = crud.get_pending_changes(db)
    assert len(changes) == 1
    assert changes[0]["by"] == "change_user"
    assert "13.10.2030" in changes[0]["text"]


def test_create_date_records_change(client, db, auth_headers, make_admin):
    make_admin("date_admin_log")

    client.post(
        "/api/duty/dates",
        json={"date_str": "14.10.2030"},
        headers=auth_headers("date_admin_log"),
    )

    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "date_admin_log" and "14.10.2030" in c["text"] for c in changes)


def test_clear_pending_changes(client, db, auth_headers, make_user):
    make_user("clear_user")

    client.post(
        "/api/duty/toggle",
        json={"date_str": "15.10.2030", "user_name": "clear_user", "value": True},
        headers=auth_headers("clear_user"),
    )

    db.rollback()
    assert len(crud.get_pending_changes(db)) == 1
    crud.clear_pending_changes(db)
    assert crud.get_pending_changes(db) == []


def test_rename_date_by_admin(client, db, auth_headers, make_admin):
    from urllib.parse import quote

    make_admin("rename_admin")
    headers = auth_headers("rename_admin")
    old_date = "25.10.2030 (утро)"
    new_date = "26.10.2030 (вечер)"
    client.post("/api/duty/dates", json={"date_str": old_date}, headers=headers)

    resp = client.put(
        f"/api/duty/dates/{quote(old_date, safe='')}",
        json={"new_date_str": "  26.10.2030   (вечер)  "},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["date_str"] == new_date
    dates = client.get("/api/duty/matrix").json()["dates"]
    assert old_date not in dates
    assert new_date in dates


def test_rename_date_keeps_duty_and_repertoire(client, db, auth_headers, make_user, make_admin):
    from urllib.parse import quote

    make_admin("rename_keep_admin")
    make_user("rename_keep_user")
    headers = auth_headers("rename_keep_admin")
    old_date = "27.10.2030"
    new_date = "28.10.2030"
    client.post("/api/duty/dates", json={"date_str": old_date}, headers=headers)
    client.post(
        "/api/duty/toggle",
        json={"date_str": old_date, "user_name": "rename_keep_user", "value": True},
        headers=headers,
    )
    client.post("/api/songs/", json={"name": "Rename Song", "text": "text"}, headers=headers)
    client.put(f"/api/repertoire/{old_date}", json={"songs": ["Rename Song"]}, headers=headers)

    resp = client.put(
        f"/api/duty/dates/{quote(old_date, safe='')}",
        json={"new_date_str": new_date},
        headers=headers,
    )

    assert resp.status_code == 200
    matrix = client.get("/api/duty/matrix").json()
    date_idx = matrix["dates"].index(new_date)
    user_idx = matrix["names"].index("rename_keep_user")
    assert matrix["matrix"][date_idx][user_idx] is True
    repertoire = client.get("/api/repertoire/").json()
    assert old_date not in repertoire
    assert [s["name"] for s in repertoire[new_date]["songs"]] == ["Rename Song"]


def test_rename_date_requires_admin(client, db, auth_headers, make_user, make_admin):
    make_user("rename_plain")
    make_admin("rename_forbid_admin")
    old_date = "29.10.2030"
    headers = auth_headers("rename_forbid_admin")
    client.post("/api/duty/dates", json={"date_str": old_date}, headers=headers)

    assert client.put(
        f"/api/duty/dates/{old_date}",
        json={"new_date_str": "30.10.2030"},
    ).status_code == 401
    resp = client.put(
        f"/api/duty/dates/{old_date}",
        json={"new_date_str": "30.10.2030"},
        headers=auth_headers("rename_plain"),
    )
    assert resp.status_code == 403
    assert old_date in client.get("/api/duty/matrix").json()["dates"]


def test_rename_date_rejects_duplicate_and_unknown(client, db, auth_headers, make_admin):
    make_admin("rename_duplicate_admin")
    headers = auth_headers("rename_duplicate_admin")
    client.post("/api/duty/dates", json={"date_str": "31.10.2030"}, headers=headers)
    client.post("/api/duty/dates", json={"date_str": "01.11.2030"}, headers=headers)

    duplicate = client.put(
        "/api/duty/dates/31.10.2030",
        json={"new_date_str": "01.11.2030"},
        headers=headers,
    )
    assert duplicate.status_code == 400

    unknown = client.put(
        "/api/duty/dates/02.11.2030",
        json={"new_date_str": "03.11.2030"},
        headers=headers,
    )
    assert unknown.status_code == 404


def test_rename_date_rejects_bad_format(client, db, auth_headers, make_admin):
    make_admin("rename_bad_admin")
    headers = auth_headers("rename_bad_admin")
    client.post("/api/duty/dates", json={"date_str": "04.11.2030"}, headers=headers)

    for new_date in ["04/11/2030", "05.11.2030 (<img src=x onerror=alert(1)>)", "05.11.2030 (а&б)"]:
        resp = client.put(
            "/api/duty/dates/04.11.2030",
            json={"new_date_str": new_date},
            headers=headers,
        )
        assert resp.status_code == 400, new_date


def test_rename_date_records_change(client, db, auth_headers, make_admin):
    make_admin("rename_log_admin")
    headers = auth_headers("rename_log_admin")
    old_date = "06.11.2030"
    new_date = "07.11.2030"
    client.post("/api/duty/dates", json={"date_str": old_date}, headers=headers)
    crud.clear_pending_changes(db)

    client.put(f"/api/duty/dates/{old_date}", json={"new_date_str": new_date}, headers=headers)

    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "rename_log_admin" and old_date in c["text"] and new_date in c["text"] for c in changes)


def test_delete_date_by_admin(client, db, auth_headers, make_admin):
    make_admin("del_admin")
    headers = auth_headers("del_admin")
    client.post("/api/duty/dates", json={"date_str": "20.10.2030"}, headers=headers)

    resp = client.delete("/api/duty/dates/20.10.2030", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "20.10.2030" not in client.get("/api/duty/matrix").json()["dates"]


def test_delete_date_with_note_urlencoded(client, db, auth_headers, make_admin):
    from urllib.parse import quote

    make_admin("del_admin_note")
    headers = auth_headers("del_admin_note")
    date_str = "22.10.2030 (утро 10-12)"
    client.post("/api/duty/dates", json={"date_str": date_str}, headers=headers)

    resp = client.delete(f"/api/duty/dates/{quote(date_str, safe='')}", headers=headers)

    assert resp.status_code == 200
    assert date_str not in client.get("/api/duty/matrix").json()["dates"]


def test_delete_date_requires_admin(client, db, auth_headers, make_user, make_admin):
    make_user("plain_del")
    make_admin("del_admin_forbid")
    client.post(
        "/api/duty/dates",
        json={"date_str": "21.10.2030"},
        headers=auth_headers("del_admin_forbid"),
    )

    assert client.delete("/api/duty/dates/21.10.2030").status_code == 401
    resp = client.delete("/api/duty/dates/21.10.2030", headers=auth_headers("plain_del"))

    assert resp.status_code == 403
    assert "21.10.2030" in client.get("/api/duty/matrix").json()["dates"]


def test_delete_unknown_date_returns_404(client, db, auth_headers, make_admin):
    make_admin("del_admin_404")

    resp = client.delete("/api/duty/dates/01.01.1999", headers=auth_headers("del_admin_404"))

    assert resp.status_code == 404


def test_delete_date_removes_children_and_forces_sync(client, db, auth_headers, make_user, make_admin):
    from app.models import DutyAssignment, DutyDate, SyncMetadata

    make_admin("del_admin_children")
    make_user("del_child_user")
    date_str = "23.10.2030"
    admin_headers = auth_headers("del_admin_children")

    client.post("/api/duty/dates", json={"date_str": date_str}, headers=admin_headers)
    client.post(
        "/api/duty/toggle",
        json={"date_str": date_str, "user_name": "del_child_user", "value": True},
        headers=admin_headers,
    )

    resp = client.delete(f"/api/duty/dates/{date_str}", headers=admin_headers)
    assert resp.status_code == 200

    db.rollback()
    assert db.query(DutyDate).filter(DutyDate.date_str == date_str).count() == 0
    # Дочерние строки должны быть удалены, а не остаться «сиротами» с date_id = NULL
    assert db.query(DutyAssignment).filter(DutyAssignment.date_id.is_(None)).count() == 0

    # Удаление не оставляет свежих updated_at, поэтому синхронизацию форсируем
    forced = db.query(SyncMetadata).filter(SyncMetadata.key == "force_full_sync").first()
    assert forced is not None
    assert forced.value == "true"


def test_delete_date_records_change(client, db, auth_headers, make_admin):
    make_admin("del_admin_log")
    date_str = "24.10.2030"
    headers = auth_headers("del_admin_log")
    client.post("/api/duty/dates", json={"date_str": date_str}, headers=headers)
    crud.clear_pending_changes(db)

    client.delete(f"/api/duty/dates/{date_str}", headers=headers)

    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "del_admin_log" and date_str in c["text"] for c in changes)
