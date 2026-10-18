import pytest
from app import crud, schemas

def test_duty_matrix(client, db):
    user = schemas.UserCreate(name="matrix_user", pin="1234")
    crud.create_user(db, user)

    # Назначаем дежурство
    payload = {
        "date_str": "15.01.2030",
        "user_name": "matrix_user",
        "value": True,
        "changer": "matrix_user",
        "pin": "1234"
    }
    client.post("/api/duty/toggle", json=payload)

    # Получаем матрицу
    response = client.get("/api/duty/matrix")
    assert response.status_code == 200
    data = response.json()
    assert "dates" in data
    assert "names" in data
    assert "matrix" in data
    assert "15.01.2030" in data["dates"]
    assert "matrix_user" in data["names"]
    # Находим индекс пользователя и проверяем, что он назначен
    idx = data["names"].index("matrix_user")
    date_idx = data["dates"].index("15.01.2030")
    assert data["matrix"][date_idx][idx] is True

def test_duty_matrix_no_duties(client):
    response = client.get("/api/duty/matrix")
    assert response.status_code == 200
    data = response.json()
    assert "dates" in data
    assert "names" in data
    assert "matrix" in data