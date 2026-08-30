from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

@router.post("/login")
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    if not crud.verify_pin(db, req.name, req.pin):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = crud.get_user_by_name(db, req.name)
    return {"success": True, "role": user.role}

@router.get("/verifyPin")
def verify_pin(name: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    valid = crud.verify_pin(db, name, pin)
    return {"success": valid}

@router.get("/getUserNames")
def get_user_names(db: Session = Depends(get_db)):
    users = db.query(crud.models.User).order_by(crud.models.User.name).all()
    names = [u.name for u in users]
    return {"names": names}

@router.get("/getUsers")
def get_users(admin_name: str = Query(...), admin_pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, admin_name, admin_pin) or not crud.is_admin(db, admin_name):
        raise HTTPException(status_code=403, detail="Admin access required")
    users = crud.get_all_users(db)
    return {"users": [{"name": u.name, "role": u.role} for u in users]}