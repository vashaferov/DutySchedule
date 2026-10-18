import os
import threading
import time
import logging
from fastapi import FastAPI, Query
from sync import main_sync
from models import User
from database import SessionLocal
from passlib.context import CryptContext
import uvicorn

app = FastAPI(title="Sync Server")
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
def run_sync(admin_name: str = Query(...), admin_pin: str = Query(...)):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.name == admin_name).first()
        if not user or not user.pin_hash or not pwd_context.verify(admin_pin, user.pin_hash):
            return {"success": False, "error": "Invalid credentials"}
        if user.role != "admin":
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
    # Раньше здесь не запускался http-сервер вообще: docker-compose запускал
    # `python sync.py --http`, а sync.py этот флаг игнорировал, поэтому
    # /api/sync/run из UI всегда получал 503 (на 8001 никто не слушал).
    threading.Thread(target=_sync_loop, daemon=True).start()
    logger.info(f"Starting sync HTTP server on :8001, interval={SYNC_INTERVAL}s")
    uvicorn.run(app, host="0.0.0.0", port=8001)
