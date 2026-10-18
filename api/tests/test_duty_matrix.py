"""
Матрица дежурств: чтение публичное, изменение — только по токену.
"""
import pytest
from app import crud, schemas


def test_duty_matrix(client, db, auth_headers, make_user):
    make_user("matrix_user")

    assign = client.post(
        "/api/duty/toggle",
        json={"date_str": "15.01.2030", "user_name": "matrix_user", "value": True},
        headers=auth_headers("matrix_user"),
    )
    assert assign.status_code == 200

    response = client.get("/api/duty/matrix")

    assert response.status_code == 200
    data = response.json()
    assert "dates" in data
    assert "names" in data
    assert "matrix" in data
    assert "15.01.2030" in data["dates"]
    assert "matrix_user" in data["names"]
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
