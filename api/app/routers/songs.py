from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

@router.get("/")
def get_songs(db: Session = Depends(get_db)):
    return crud.get_all_songs(db)

@router.post("/")
def create_song(song: schemas.SongCreate, changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        created = crud.create_song(db, song)
        crud.set_sync_flag(db, True, changer, f"добавлена песня «{created.name}»")
        # Явный словарь: set_sync_flag коммитит и «протухает» ORM-объект,
        # из-за чего FastAPI сериализовал бы пустой __dict__.
        return {"id": created.id, "name": created.name, "text": created.text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{name}")
def update_song_text(name: str, new_text: str = Query(...), changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        song = crud.update_song_text(db, name, new_text)
        crud.set_sync_flag(db, True, changer, f"изменён текст песни «{name}»")
        return {"success": True, "song": schemas.SongResponse.model_validate(song)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{name}")
def delete_song(name: str, changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        crud.delete_song(db, name)
        crud.set_sync_flag(db, True, changer, f"удалена песня «{name}»")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))