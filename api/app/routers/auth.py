from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, models, ratelimit, schemas
from ..security import create_token, get_current_user, require_admin

router = APIRouter()

@router.post("/login")
def login(req: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Единственное место, куда клиент присылает PIN. В ответ уходит токен."""
    ip = ratelimit.client_ip(request)
    # Лимит проверяем до сверки PIN: иначе перебор четырёхзначного PIN ничего
    # не стоит — правильность PIN узнаётся из ответа, а попытки не считаются.
    ratelimit.check(db, req.name, ip)
    if not crud.verify_pin(db, req.name, req.pin):
        ratelimit.record_failure(db, req.name, ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ratelimit.clear_failures(db, req.name)
    user = crud.get_user_by_name(db, req.name)
    return {
        "success": True,
        "role": user.role,
        "token": create_token(user.name, user.role),
    }

@router.get("/me")
def me(user: models.User = Depends(get_current_user)):
    """Проверка сохранённого токена при загрузке страницы."""
    return {"name": user.name, "role": user.role}

@router.get("/getUserNames")
def get_user_names(db: Session = Depends(get_db)):
    users = db.query(crud.models.User).order_by(crud.models.User.name).all()
    return {"names": [u.name for u in users]}

@router.get("/getUsers")
def get_users(user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    users = crud.get_all_users(db)
    return {"users": [{"name": u.name, "role": u.role} for u in users]}
