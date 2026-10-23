import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, models, schemas
from ..security import get_current_user, require_admin

router = APIRouter()

# "10.10.2026" или "10.10.2026 (утро 10-12)".
# В примечании запрещены символы, которыми можно разметить HTML, сломать URL-путь
# или подсунуть управляющие последовательности. Экранирование на выводе — основная
# защита, это лишь дополнительный барьер (и заодно запрет мусорных дат).
DATE_STR_RE = re.compile(r'^\d{2}\.\d{2}\.\d{4}(\s*\([^<>"\'`&/\\#?\x00-\x1f]+\))?$')


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
def create_date(req: schemas.DutyDateCreateRequest,
                user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    date_str = normalize_date_str(req.date_str)
    if not DATE_STR_RE.match(date_str):
        raise HTTPException(
            status_code=400,
            detail='Формат даты: ДД.ММ.ГГГГ (пояснение в скобках). '
                   'В пояснении нельзя символы < > " \' & / # ?',
        )
    try:
        crud.create_date(db, date_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    crud.set_sync_flag(db, True, user.name, f"добавлена дата {date_str}")
    return {"success": True, "date_str": date_str}

@router.put("/dates/{date_str}")
def rename_date(
    date_str: str,
    req: schemas.DutyDateRenameRequest,
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    old_date_str = normalize_date_str(date_str)
    new_date_str = normalize_date_str(req.new_date_str)
    if not DATE_STR_RE.match(new_date_str):
        raise HTTPException(
            status_code=400,
            detail='Формат даты: ДД.ММ.ГГГГ (пояснение в скобках). '
                   'В пояснении нельзя символы < > " \' & / # ?',
        )
    try:
        crud.rename_date(db, old_date_str, new_date_str)
    except ValueError as e:
        status_code = 404 if str(e) == "Дата не найдена" else 400
        raise HTTPException(status_code=status_code, detail=str(e))

    crud.set_sync_flag(db, True, user.name, f"переименована дата {old_date_str} → {new_date_str}")
    return {"success": True, "old_date_str": old_date_str, "date_str": new_date_str}


@router.delete("/dates/{date_str}")
def delete_date(
    date_str: str,
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    date_str = normalize_date_str(date_str)
    try:
        crud.delete_date(db, date_str)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Удалённые строки не оставляют нового updated_at, поэтому обычная проверка
    # изменений в sync не сработает — просим перезалить листы целиком.
    crud.set_force_full_sync(db, True)
    crud.set_sync_flag(db, True, user.name, f"удалена дата {date_str}")
    return {"success": True, "date_str": date_str}

@router.post("/toggle")
def toggle_duty(req: schemas.DutyToggleRequest,
                user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    # Менять можно только своё дежурство; администратор — любое.
    if user.role != "admin" and user.name != req.user_name:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        crud.toggle_duty(db, req.date_str, req.user_name, req.value)
        action = 'назначено' if req.value else 'снято'
        crud.set_sync_flag(db, True, user.name, f"дежурство {req.date_str}: {req.user_name} — {action}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
