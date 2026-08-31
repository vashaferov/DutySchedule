from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

@router.get("/")
def get_users(admin_name: str = Query(...), admin_pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    users = crud.get_all_users(db)
    return [{"name": u.name, "role": u.role} for u in users]

@router.put("/{name}/pin")
def update_user_pin(name: str, new_pin: str = Query(...), admin_name: str = Query(...), admin_pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        user = crud.update_user_pin(db, name, new_pin)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/")
def create_user(name: str = Query(...), pin: str = Query(...), role: str = Query('user'),
                admin_name: str = Query(...), admin_pin: str = Query(...),
                db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        user = crud.create_user(db, name, pin, role)
        return {"success": True, "user": {"name": user.name, "role": user.role}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{name}")
def delete_user(name: str, admin_name: str = Query(...), admin_pin: str = Query(...),
                db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        crud.delete_user(db, name)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{name}/role")
def update_user_role(name: str, role: str = Query(...), admin_name: str = Query(...), admin_pin: str = Query(...),
                     db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    if role not in ['user', 'admin']:
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        user = crud.update_user_role(db, name, role)
        return {"success": True, "user": {"name": user.name, "role": user.role}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))