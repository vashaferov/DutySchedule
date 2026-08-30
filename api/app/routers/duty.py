from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

@router.get("/matrix")
def get_duty_matrix(db: Session = Depends(get_db)):
    dates = crud.get_all_dates(db)
    users = db.query(crud.models.User).order_by(crud.models.User.name).all()
    names = [u.name for u in users]
    date_strs = [d.date_str for d in dates]
    matrix = []
    for date in dates:
        assignments = {ass.user_id for ass in date.assignments}
        row = [u.id in assignments for u in users]
        matrix.append(row)
    return {"dates": date_strs, "names": names, "matrix": matrix}

@router.post("/toggle")
def toggle_duty(req: schemas.DutyToggleRequest, db: Session = Depends(get_db)):
    # Проверка авторизации (вызов crud.verify_pin)
    if not crud.verify_pin(db, req.changer, req.pin):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    if not crud.is_admin(db, req.changer) and req.changer != req.user_name:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        crud.toggle_duty(db, req.date_str, req.user_name, req.value)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))