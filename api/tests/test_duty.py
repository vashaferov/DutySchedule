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