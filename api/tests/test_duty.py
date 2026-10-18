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