from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, models, schemas
from ..security import require_admin

router = APIRouter()

@router.get("/")
def get_users(user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    users = crud.get_all_users(db)
    return [{"name": u.name, "role": u.role} for u in users]

@router.put("/{name}/pin")
def update_user_pin(name: str, req: schemas.UserPinUpdateRequest,
                    user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        crud.update_user_pin(db, name, req.new_pin)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/")
def create_user(req: schemas.UserCreateRequest,
                user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    if req.role not in ('user', 'admin'):
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        created = crud.create_user(db, schemas.UserCreate(name=req.name, pin=req.pin))
        # Роль раньше молча игнорировалась: приходилось отдельным запросом
        # досылать PUT /{name}/role.
        if req.role != 'user':
            crud.update_user_role(db, req.name, req.role)
        return {"success": True, "user": {"name": created.name, "role": req.role}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{name}")
def delete_user(name: str, user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        crud.delete_user(db, name)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{name}/role")
def update_user_role(name: str, req: schemas.UserRoleUpdateRequest,
                     user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    if req.role not in ('user', 'admin'):
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        crud.update_user_role(db, name, req.role)
        return {"success": True, "user": {"name": name, "role": req.role}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
