from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud

router = APIRouter()

@router.get("/history")
def get_history(admin_name: str = Query(...), admin_pin: str = Query(...), limit: int = 50, db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    history = crud.get_sync_history(db, limit)
    return history