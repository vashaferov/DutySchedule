"""Авторизация по токену вместо PIN в каждом запросе.

Раньше почти каждая ручка принимала pin/admin_pin в query string, и PIN попадал
в access-логи nginx — именно так он и всплыл при разборе инцидента 17.10.2026.
Теперь клиент один раз меняет PIN на подписанный токен (POST /api/auth/login)
и дальше присылает его в заголовке `Authorization: Bearer <token>`.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .database import get_db

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
# Срок жизни токена. Выход из приложения не «сжигает» токен (серверного списка
# сессий нет), поэтому срок должен быть ограничен.
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "168"))


def _load_secret_key() -> str:
    key = (os.getenv("SECRET_KEY") or "").strip()
    if key:
        return key
    # Пустой ключ не должен превращаться в отказ сервиса: недоступное приложение
    # хуже, чем разлогин после перезапуска. В деплое ключ генерируется и лежит в .env.
    logger.warning(
        "SECRET_KEY не задан — сгенерирован временный ключ. Токены перестанут "
        "действовать после перезапуска API. Задайте JWT_SECRET в секретах GitHub "
        "или SECRET_KEY в .env."
    )
    return secrets.token_urlsafe(32)


SECRET_KEY = _load_secret_key()

# auto_error=False: отсутствие заголовка обрабатываем сами, чтобы вернуть 401
# с понятным текстом, а не 403 от FastAPI.
bearer_scheme = HTTPBearer(auto_error=False)


def create_token(name: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": name,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла, войдите заново",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    name = payload.get("sub")
    if not name:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный токен")

    # Роль берём из базы, а не из токена: разжалованный админ должен потерять
    # права сразу, не дожидаясь истечения токена. Удалённый пользователь — тоже.
    user = db.query(models.User).filter(models.User.name == name).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
