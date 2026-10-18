def test_toggle_duty(client, db):
    from app import crud, schemas
    
    user = schemas.UserCreate(name="duty_user", pin="1234")
    crud.create_user(db, user)
    
    payload = {
        "date_str": "01.01.2030",
        "user_name": "duty_user",
        "value": True,
        "changer": "duty_user",
        "pin": "1234"
    }
    response = client.post("/api/duty/toggle", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Проверяем, что назначение появилось
    matrix_resp = client.get("/api/duty/matrix")
    assert matrix_resp.status_code == 200
    data = matrix_resp.json()
    assert "01.01.2030" in data["dates"]
    # Проверяем, что пользователь назначен на эту дату

def test_toggle_duty_remove(client, db):
    from app import crud, schemas
    
    user = schemas.UserCreate(name="duty_user2", pin="1234")
    crud.create_user(db, user)
    
    # Сначала назначаем
    payload_add = {
        "date_str": "02.01.2030",
        "user_name": "duty_user2",
        "value": True,
        "changer": "duty_user2",
        "pin": "1234"
    }
    client.post("/api/duty/toggle", json=payload_add)
    
    # Убираем
    payload_remove = {
        "date_str": "02.01.2030",
        "user_name": "duty_user2",
        "value": False,
        "changer": "duty_user2",
        "pin": "1234"
    }
    response = client.post("/api/duty/toggle", json=payload_remove)
    assert response.status_code == 200
    assert response.json()["success"] is True


def _make_admin(db, name, pin="1234"):
    from app import crud, schemas
    crud.create_user(db, schemas.UserCreate(name=name, pin=pin))
    crud.update_user_role(db, name, "admin")
    return name


def test_create_date_by_admin(client, db):
    _make_admin(db, "date_admin")
    resp = client.post("/api/duty/dates", json={
        "date_str": "10.10.2030 (утро 10-12)",
        "changer": "date_admin",
        "pin": "1234",
    })
    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2030 (утро 10-12)"

    matrix = client.get("/api/duty/matrix").json()
    assert "10.10.2030 (утро 10-12)" in matrix["dates"]


def test_create_date_normalizes_spaces(client, db):
    _make_admin(db, "date_admin_norm")
    resp = client.post("/api/duty/dates", json={
        "date_str": "  10.10.2031 (утро   10-12)  ",
        "changer": "date_admin_norm",
        "pin": "1234",
    })
    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2031 (утро 10-12)"


def test_create_date_requires_admin(client, db):
    from app import crud, schemas
    crud.create_user(db, schemas.UserCreate(name="plain_dates", pin="1234"))
    resp = client.post("/api/duty/dates", json={
        "date_str": "11.10.2030", "changer": "plain_dates", "pin": "1234"})
    assert resp.status_code == 403


def test_create_date_rejects_bad_format(client, db):
    _make_admin(db, "date_admin_bad")
    resp = client.post("/api/duty/dates", json={
        "date_str": "10/10/2030", "changer": "date_admin_bad", "pin": "1234"})
    assert resp.status_code == 400


def test_create_date_rejects_html_in_note(client, db):
    """Примечание к дате — это был вектор stored XSS, HTML туда проходить не должен."""
    _make_admin(db, "date_admin_xss")
    payloads = [
        "10.10.2032 (<img src=x onerror=alert(1)>)",
        '10.10.2032 (" onmouseover="alert(1))',
        "10.10.2032 (<script>alert(1)</script>)",
        "10.10.2032 (а/b)",
        "10.10.2032 (а&б)",
    ]
    for date_str in payloads:
        resp = client.post("/api/duty/dates", json={
            "date_str": date_str, "changer": "date_admin_xss", "pin": "1234"})
        assert resp.status_code == 400, date_str

    dates = client.get("/api/duty/matrix").json()["dates"]
    assert not any("<" in d or ">" in d for d in dates)


def test_create_date_accepts_safe_note_chars(client, db):
    """Обычные примечания (запятые, двоеточия, тире, №) по-прежнему принимаются."""
    _make_admin(db, "date_admin_ok_note")
    resp = client.post("/api/duty/dates", json={
        "date_str": " 10.10.2033 (вечер, 18:00-20:00 — по заявке №5) ",
        "changer": "date_admin_ok_note", "pin": "1234"})
    assert resp.status_code == 200
    assert resp.json()["date_str"] == "10.10.2033 (вечер, 18:00-20:00 — по заявке №5)"


def test_create_date_rejects_duplicate(client, db):
    _make_admin(db, "date_admin_dup")
    payload = {"date_str": "12.10.2030", "changer": "date_admin_dup", "pin": "1234"}
    assert client.post("/api/duty/dates", json=payload).status_code == 200
    assert client.post("/api/duty/dates", json=payload).status_code == 400


def test_toggle_records_change(client, db):
    from app import crud, schemas
    crud.create_user(db, schemas.UserCreate(name="change_user", pin="1234"))

    client.post("/api/duty/toggle", json={
        "date_str": "13.10.2030", "user_name": "change_user",
        "value": True, "changer": "change_user", "pin": "1234"})

    db.rollback()  # берём свежие данные из БД
    changes = crud.get_pending_changes(db)
    assert len(changes) == 1
    assert changes[0]["by"] == "change_user"
    assert "13.10.2030" in changes[0]["text"]


def test_create_date_records_change(client, db):
    from app import crud
    _make_admin(db, "date_admin_log")

    client.post("/api/duty/dates", json={
        "date_str": "14.10.2030", "changer": "date_admin_log", "pin": "1234"})

    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "date_admin_log" and "14.10.2030" in c["text"] for c in changes)


def test_clear_pending_changes(client, db):
    from app import crud, schemas
    crud.create_user(db, schemas.UserCreate(name="clear_user", pin="1234"))

    client.post("/api/duty/toggle", json={
        "date_str": "15.10.2030", "user_name": "clear_user",
        "value": True, "changer": "clear_user", "pin": "1234"})

    db.rollback()
    assert len(crud.get_pending_changes(db)) == 1
    crud.clear_pending_changes(db)
    assert crud.get_pending_changes(db) == []


def test_delete_date_by_admin(client, db):
    _make_admin(db, "del_admin")
    client.post("/api/duty/dates", json={
        "date_str": "20.10.2030", "changer": "del_admin", "pin": "1234"})

    resp = client.delete("/api/duty/dates/20.10.2030?changer=del_admin&pin=1234")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert "20.10.2030" not in client.get("/api/duty/matrix").json()["dates"]


def test_delete_date_with_note_urlencoded(client, db):
    from urllib.parse import quote

    _make_admin(db, "del_admin_note")
    date_str = "22.10.2030 (утро 10-12)"
    client.post("/api/duty/dates", json={
        "date_str": date_str, "changer": "del_admin_note", "pin": "1234"})

    resp = client.delete(
        f"/api/duty/dates/{quote(date_str, safe='')}?changer=del_admin_note&pin=1234"
    )

    assert resp.status_code == 200
    assert date_str not in client.get("/api/duty/matrix").json()["dates"]


def test_delete_date_requires_admin(client, db):
    from app import crud, schemas
    crud.create_user(db, schemas.UserCreate(name="plain_del", pin="1234"))
    _make_admin(db, "del_admin_forbid")
    client.post("/api/duty/dates", json={
        "date_str": "21.10.2030", "changer": "del_admin_forbid", "pin": "1234"})

    resp = client.delete("/api/duty/dates/21.10.2030?changer=plain_del&pin=1234")

    assert resp.status_code == 403
    assert "21.10.2030" in client.get("/api/duty/matrix").json()["dates"]


def test_delete_unknown_date_returns_404(client, db):
    _make_admin(db, "del_admin_404")

    resp = client.delete("/api/duty/dates/01.01.1999?changer=del_admin_404&pin=1234")

    assert resp.status_code == 404


def test_delete_date_removes_children_and_forces_sync(client, db):
    from app import crud, schemas
    from app.models import DutyAssignment, DutyDate, SyncMetadata

    _make_admin(db, "del_admin_children")
    crud.create_user(db, schemas.UserCreate(name="del_child_user", pin="1234"))
    date_str = "23.10.2030"

    client.post("/api/duty/dates", json={
        "date_str": date_str, "changer": "del_admin_children", "pin": "1234"})
    client.post("/api/duty/toggle", json={
        "date_str": date_str, "user_name": "del_child_user",
        "value": True, "changer": "del_admin_children", "pin": "1234"})

    resp = client.delete(f"/api/duty/dates/{date_str}?changer=del_admin_children&pin=1234")
    assert resp.status_code == 200

    db.rollback()
    assert db.query(DutyDate).filter(DutyDate.date_str == date_str).count() == 0
    # Дочерние строки должны быть удалены, а не остаться «сиротами» с date_id = NULL
    assert db.query(DutyAssignment).filter(DutyAssignment.date_id.is_(None)).count() == 0

    # Удаление не оставляет свежих updated_at, поэтому синхронизацию форсируем
    forced = db.query(SyncMetadata).filter(SyncMetadata.key == "force_full_sync").first()
    assert forced is not None
    assert forced.value == "true"


def test_delete_date_records_change(client, db):
    from app import crud

    _make_admin(db, "del_admin_log")
    date_str = "24.10.2030"
    client.post("/api/duty/dates", json={
        "date_str": date_str, "changer": "del_admin_log", "pin": "1234"})
    crud.clear_pending_changes(db)

    client.delete(f"/api/duty/dates/{date_str}?changer=del_admin_log&pin=1234")

    db.rollback()
    changes = crud.get_pending_changes(db)
    assert any(c["by"] == "del_admin_log" and date_str in c["text"] for c in changes)