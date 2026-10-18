from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, models, schemas
from ..security import require_admin

router = APIRouter()

@router.get("/")
def get_songs(db: Session = Depends(get_db)):
    return crud.get_all_songs(db)

@router.post("/")
def create_song(song: schemas.SongCreate,
                user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    try:
        created = crud.create_song(db, song)
        crud.set_sync_flag(db, True, user.name, f"добавлена песня «{created.name}»")
        # Явный словарь: set_sync_flag коммитит и «протухает» ORM-объект,
        # из-за чего FastAPI сериализовал бы пустой __dict__.
        return {"id": created.id, "name": created.name, "text": created.text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{name}")
def update_song_text(name: str, req: schemas.SongTextUpdateRequest,
                     user: models.User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    # Текст песни — в теле запроса, а не в query: полный текст песни легко
    # превышает лимит длины URL nginx.
    try:
        song = crud.update_song_text(db, name, req.text)
        crud.set_sync_flag(db, True, user.name, f"изменён текст песни «{name}»")
        return {"success": True, "song": schemas.SongResponse.model_validate(song)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{name}")
def delete_song(name: str,
                user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    try:
        crud.delete_song(db, name)
        crud.set_sync_flag(db, True, user.name, f"удалена песня «{name}»")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
