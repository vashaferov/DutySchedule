from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, models, schemas
from ..security import require_admin

router = APIRouter()

@router.get("/history", response_model=List[schemas.SyncHistoryResponse])
def get_history(limit: int = 50,
                user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    return crud.get_sync_history(db, limit)
