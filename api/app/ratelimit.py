"""Ограничение попыток входа.

PIN — четыре цифры, то есть всего 10 000 комбинаций. Пока лимита не было,
подобрать чужой PIN скриптом было делом десятков минут: обработчик отвечал
401 и ничем не мешал перебирать дальше.

Здесь неудачные попытки считаются в скользящем окне — отдельно по имени
пользователя и отдельно по IP:

* порог на пользователя (по умолчанию 5) не даёт перебирать один PIN;
* порог на IP (по умолчанию 60, заведомо выше офисного) ловит перебор
  «по всем сразу» с одного адреса, при этом не блокирует коллег,
  которые сидят за общим адресом и просто опечатались.

Счётчики лежат в БД (таблица `login_attempts`), а не в памяти процесса:
перезапуск API не должен обнулять историю неудач, и при разборе инцидента
должно быть видно, что вход пытались подобрать. Строки старше окна удаляются
при каждой записи, поэтому таблица ограничена по размеру.

Пороги читаются из окружения на каждом запросе:
    LOGIN_MAX_FAILURES_PER_USER (по умолчанию 5)
    LOGIN_MAX_FAILURES_PER_IP   (по умолчанию 60)
    LOGIN_WINDOW_MINUTES        (по умолчанию 15)
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger(__name__)

DEFAULT_MAX_FAILURES_PER_USER = 5
DEFAULT_MAX_FAILURES_PER_IP = 60
DEFAULT_WINDOW_MINUTES = 15


def _positive_int(name: str, default: int) -> int:
    """Читает настройку из окружения. Мусор в переменной не должен ломать вход."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r — не число, беру значение по умолчанию %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%d — должно быть больше нуля, беру %d", name, value, default)
        return default
    return value


def window() -> timedelta:
    return timedelta(minutes=_positive_int("LOGIN_WINDOW_MINUTES", DEFAULT_WINDOW_MINUTES))


def max_failures_per_user() -> int:
    return _positive_int("LOGIN_MAX_FAILURES_PER_USER", DEFAULT_MAX_FAILURES_PER_USER)


def max_failures_per_ip() -> int:
    return _positive_int("LOGIN_MAX_FAILURES_PER_IP", DEFAULT_MAX_FAILURES_PER_IP)


def client_ip(request: Request) -> str:
    """IP клиента из заголовка nginx.

    Порт API наружу не публикуется, единственный вход — nginx, а он ставит
    X-Real-IP значением $remote_addr через proxy_set_header (то есть значение
    перезаписывается, подделать его клиент не может).
    """
    real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip[:64]
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _now() -> datetime:
    """UTC без зоны — в таком же виде время лежит в БД.

    Сравнивать нужно свои значения, а не `func.now()`: в тестах это SQLite,
    в проде — Postgres, и вычитание интервала переносимо только через Python.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count(db: Session, column, value: str, cutoff: datetime) -> int:
    return (
        db.query(func.count(models.LoginAttempt.id))
        .filter(models.LoginAttempt.attempted_at >= cutoff, column == value)
        .scalar()
        or 0
    )


def _retry_after_seconds(db: Session, name: str, ip: str) -> int:
    """Сколько ждать до следующей попытки.

    Отпустит, когда самая старая неудача из окна (по этому пользователю или по
    этому IP) выйдет за его границу.
    """
    cutoff = _now() - window()
    oldest = (
        db.query(func.min(models.LoginAttempt.attempted_at))
        .filter(models.LoginAttempt.attempted_at >= cutoff)
        .filter((models.LoginAttempt.username == name) | (models.LoginAttempt.ip == ip))
        .scalar()
    )
    if oldest is None:
        return 0
    return max(1, int(((oldest + window()) - _now()).total_seconds()))


def _raise_too_many(db: Session, name: str, ip: str, reason: str) -> None:
    seconds = _retry_after_seconds(db, name, ip)
    logger.warning(
        "Вход заблокирован лимитом попыток (%s): пользователь=%r ip=%s, ждать %d с",
        reason, name, ip, seconds,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            "Слишком много неудачных попыток входа. "
            f"Повторите примерно через {max(1, seconds // 60)} мин."
        ),
        headers={"Retry-After": str(seconds)},
    )


def check(db: Session, name: str, ip: str) -> None:
    """Бросает 429, если попытки пора прекратить.

    Вызывается до сверки PIN: иначе перебор был бы бесплатным.
    """
    cutoff = _now() - window()
    if _count(db, models.LoginAttempt.username, name, cutoff) >= max_failures_per_user():
        _raise_too_many(db, name, ip, "много неудач у пользователя")
    if _count(db, models.LoginAttempt.ip, ip, cutoff) >= max_failures_per_ip():
        _raise_too_many(db, name, ip, "много неудач с одного IP")


def record_failure(db: Session, name: str, ip: str) -> None:
    """Записывает неудачу и попутно подчищает то, что уже вышло из окна."""
    now = _now()
    db.query(models.LoginAttempt).filter(
        models.LoginAttempt.attempted_at < now - window()
    ).delete(synchronize_session=False)
    db.add(models.LoginAttempt(username=(name or "")[:100], ip=ip, attempted_at=now))
    db.commit()
    logger.warning("Неудачная попытка входа: пользователь=%r ip=%s", name, ip)


def clear_failures(db: Session, name: str) -> None:
    """Успешный вход обнуляет счётчик — но только этого пользователя.

    Иначе один человек, опечатавшийся пять раз, блокировал бы вход коллегам
    с того же офисного IP.
    """
    deleted = (
        db.query(models.LoginAttempt)
        .filter(models.LoginAttempt.username == name)
        .delete(synchronize_session=False)
    )
    db.commit()
    if deleted:
        logger.info("Успешный вход %r — счётчик неудач сброшен (%d)", name, deleted)
