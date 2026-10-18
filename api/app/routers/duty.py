import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

# "10.10.2026" или "10.10.2026 (утро 10-12)"
DATE_STR_RE = re.compile(r'^\d{2}\.\d{2}\.\d{4}(\s*\(.+\))?$')


def normalize_date_str(raw: str) -> str:
    return ' '.join((raw or '').split())


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

@router.post("/dates")
def create_date(req: schemas.DutyDateCreateRequest, db: Session = Depends(get_db)):
    # Заводить даты можно только от имени администратора.
    if not crud.verify_pin(db, req.changer, req.pin) or not crud.is_admin(db, req.changer):
        raise HTTPException(status_code=403, detail="Admin access required")

    date_str = normalize_date_str(req.date_str)
    if not DATE_STR_RE.match(date_str):
        raise HTTPException(
            status_code=400,
            detail="Формат даты: ДД.ММ.ГГГГ (пояснение в скобках — по желанию)",
        )
    try:
        crud.create_date(db, date_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    crud.set_sync_flag(db, True, req.changer, f"добавлена дата {date_str}")
    return {"success": True, "date_str": date_str}

@router.post("/toggle")
def toggle_duty(req: schemas.DutyToggleRequest, db: Session = Depends(get_db)):
    # Проверка авторизации (вызов crud.verify_pin)
    if not crud.verify_pin(db, req.changer, req.pin):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    if not crud.is_admin(db, req.changer) and req.changer != req.user_name:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        crud.toggle_duty(db, req.date_str, req.user_name, req.value)
        action = 'назначено' if req.value else 'снято'
        crud.set_sync_flag(db, True, req.changer, f"дежурство {req.date_str}: {req.user_name} — {action}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
