"""Ограничение попыток входа.

PIN четырёхзначный, поэтому перебор надо ограничивать: иначе скрипт подбирает
чужой PIN за минуты. Здесь проверяем, что лимит срабатывает, что нормальному
входу он не мешает, что он не блокирует коллег с общего адреса и что сам
отпускает пользователя, когда окно проходит.
"""
from datetime import datetime, timedelta, timezone

from app import models, ratelimit

LOGIN = "/api/auth/login"
WRONG_PIN = "9999"
RIGHT_PIN = "1234"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fail_login(client, name, ip=None):
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post(LOGIN, json={"name": name, "pin": WRONG_PIN}, headers=headers)


def ok_login(client, name, ip=None):
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post(LOGIN, json={"name": name, "pin": RIGHT_PIN}, headers=headers)


def test_normal_login_is_not_limited(client, make_user):
    make_user("rl_ok", pin=RIGHT_PIN)
    for _ in range(3):
        assert fail_login(client, "rl_ok").status_code == 401
    assert ok_login(client, "rl_ok").status_code == 200


def test_many_successful_logins_are_fine(client, make_user):
    """Успешные входы не считаются неудачами — иначе офис заблокировал бы себя."""
    make_user("rl_success", pin=RIGHT_PIN)
    for _ in range(10):
        assert ok_login(client, "rl_success").status_code == 200


def test_blocks_after_five_failures(client, make_user):
    make_user("rl_block", pin=RIGHT_PIN)
    for attempt in range(1, 6):
        assert fail_login(client, "rl_block").status_code == 401, f"попытка {attempt}"

    # Шестая — уже без сверки PIN: даже правильный получает 429.
    blocked = ok_login(client, "rl_block")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) > 0
    assert "мин" in blocked.json()["detail"]


def test_counter_is_per_user(client, make_user):
    """Заблокированный не тянет за собой остальных."""
    make_user("rl_a", pin=RIGHT_PIN)
    make_user("rl_b", pin=RIGHT_PIN)
    for _ in range(5):
        fail_login(client, "rl_a")
    assert ok_login(client, "rl_a").status_code == 429
    assert ok_login(client, "rl_b").status_code == 200


def test_success_resets_counter(client, make_user):
    make_user("rl_reset", pin=RIGHT_PIN)
    for _ in range(4):
        fail_login(client, "rl_reset")
    assert ok_login(client, "rl_reset").status_code == 200
    # счётчик начался заново: снова можно ошибиться четыре раза
    for _ in range(4):
        assert fail_login(client, "rl_reset").status_code == 401


def test_releases_after_window(client, db, make_user):
    """Лимит отпускает сам, без вмешательства админа."""
    make_user("rl_release", pin=RIGHT_PIN)
    for _ in range(5):
        fail_login(client, "rl_release")
    assert ok_login(client, "rl_release").status_code == 429

    # «Прокручиваем» окно: ждать 15 минут в тесте нельзя, поэтому сдвигаем
    # записанные неудачи назад во времени.
    db.query(models.LoginAttempt).update(
        {models.LoginAttempt.attempted_at: utc_now() - timedelta(minutes=30)}
    )
    db.commit()
    assert ok_login(client, "rl_release").status_code == 200


def test_old_failures_do_not_count(client, db, make_user):
    """Неудачи из прошлого окна не блокируют вход."""
    make_user("rl_old", pin=RIGHT_PIN)
    for _ in range(10):
        db.add(models.LoginAttempt(
            username="rl_old", ip="10.0.0.1", attempted_at=utc_now() - timedelta(minutes=30)
        ))
    db.commit()
    assert ok_login(client, "rl_old").status_code == 200


def test_ip_taken_from_nginx_header(client, db, make_user):
    """За nginx request.client.host — это сам nginx, поэтому берём X-Real-IP."""
    make_user("rl_ip", pin=RIGHT_PIN)
    fail_login(client, "rl_ip", ip="203.0.113.5")
    row = db.query(models.LoginAttempt).order_by(models.LoginAttempt.id.desc()).first()
    assert row.ip == "203.0.113.5"


def test_ip_limit_catches_spraying(client, monkeypatch, make_user):
    """Перебор по многим именам с одного адреса упирается в отдельный порог."""
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_IP", "3")
    ip = "198.51.100.7"
    for i in range(3):
        assert fail_login(client, f"rl_spray_{i}", ip=ip).status_code == 401

    blocked = fail_login(client, "rl_spray_more", ip=ip)
    assert blocked.status_code == 429
    # с другого адреса проверка обычная: это не блокировка пользователя
    assert fail_login(client, "rl_spray_more", ip="198.51.100.8").status_code == 401


def test_default_ip_limit_does_not_hurt_shared_office(client, make_user):
    """Порог на IP по умолчанию заведомо выше офисного.

    Если бы он был маленьким, один человек, ошибающийся пять раз, мешал бы
    входить коллегам с того же адреса.
    """
    assert ratelimit.max_failures_per_ip() == 60
    make_user("rl_office_a", pin=RIGHT_PIN)
    make_user("rl_office_b", pin=RIGHT_PIN)
    for _ in range(5):
        fail_login(client, "rl_office_a")
    assert ok_login(client, "rl_office_b").status_code == 200


def test_limits_are_configurable(client, monkeypatch, make_user):
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_USER", "2")
    make_user("rl_cfg", pin=RIGHT_PIN)
    assert fail_login(client, "rl_cfg").status_code == 401
    assert fail_login(client, "rl_cfg").status_code == 401
    assert ok_login(client, "rl_cfg").status_code == 429


def test_garbage_env_falls_back_to_defaults(monkeypatch):
    """Кривое значение в .env не должно ломать вход."""
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_USER", "много")
    assert ratelimit.max_failures_per_user() == ratelimit.DEFAULT_MAX_FAILURES_PER_USER

    monkeypatch.setenv("LOGIN_WINDOW_MINUTES", "0")
    assert ratelimit.window() == timedelta(minutes=ratelimit.DEFAULT_WINDOW_MINUTES)

    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_IP", "")
    assert ratelimit.max_failures_per_ip() == ratelimit.DEFAULT_MAX_FAILURES_PER_IP


def test_long_name_does_not_break_recording(client, db):
    """Имя из запроса не проверяется схемой до конца — обрезаем его сами."""
    response = client.post(LOGIN, json={"name": "x" * 300, "pin": WRONG_PIN})
    assert response.status_code == 401
    row = db.query(models.LoginAttempt).order_by(models.LoginAttempt.id.desc()).first()
    assert len(row.username) == 100
