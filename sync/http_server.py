from fastapi import FastAPI, Query
from sync import main_sync
from models import User
from database import SessionLocal
from passlib.context import CryptContext
import logging
import uvicorn

app = FastAPI(title="Sync Server")
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        main_sync()
        return {"success": True, "message": "Sync completed"}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)