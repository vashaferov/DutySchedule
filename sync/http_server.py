import os
import threading
import time
import logging
from typing import Optional
from fastapi import FastAPI, Header
from jose import JWTError, jwt
from sync import main_sync
from models import Base, User
from database import SessionLocal, engine
import uvicorn

app = FastAPI(title="Sync Server")
logger = logging.getLogger(__name__)

# Тот же ключ, что у API: sync проверяет токен, который API передал как есть.
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
ALGORITHM = "HS256"


def _user_from_token(token: str) -> Optional[str]:
    """Проверяет подпись токена API и возвращает имя пользователя."""
    if not SECRET_KEY:
        logger.error(
            "SECRET_KEY не задан — проверить токен нельзя, ручной запуск синхронизации отключён. "
            "Задайте JWT_SECRET в секретах GitHub (деплой прокидывает его в .env)."
        )
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")


# Периодичность фоновой синхронизации (в sync.py было жёстко 30).
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "30"))

# main_sync() ходит в одну и ту же Google-таблицу, поэтому фоновый цикл и
# кнопка «Синхронизировать» в UI не должны выполняться одновременно.
_sync_lock = threading.Lock()


def _sync_loop():
    """Фоновый автосинк: сам проверяет флаг sync_flag внутри main_sync()."""
    while True:
        try:
            with _sync_lock:
                main_sync()
        except Exception as e:
            logger.error(f"Background sync loop error: {e}")
        time.sleep(SYNC_INTERVAL)


@app.post("/run")
def run_sync(authorization: Optional[str] = Header(default=None)):
    # Раньше здесь проверялся admin_pin из query. Теперь API присылает токен
    # вызывающего: PIN по сети не ходит вообще.
    token = ''
    if authorization and authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
    name = _user_from_token(token)
    if not name:
        return {"success": False, "error": "Unauthorized"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.name == name).first()
        if not user or user.role != "admin":
            return {"success": False, "error": "Admin access required"}
    finally:
        db.close()

    try:
        with _sync_lock:
            main_sync()
        return {"success": True, "message": "Sync completed"}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # На пустой БД sync мог стартовать раньше api и падать с
    # "relation ... does not exist". Создаём недостающие таблицы сами:
    # операция идемпотентная, существующую схему не меняет.
    Base.metadata.create_all(bind=engine)

    # Раньше здесь не запускался http-сервер вообще: docker-compose запускал
    # `python sync.py --http`, а sync.py этот флаг игнорировал, поэтому
    # /api/sync/run из UI всегда получал 503 (на 8001 никто не слушал).
    threading.Thread(target=_sync_loop, daemon=True).start()
    logger.info(f"Starting sync HTTP server on :8001, interval={SYNC_INTERVAL}s")
    uvicorn.run(app, host="0.0.0.0", port=8001)
