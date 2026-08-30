from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from .. import crud, schemas

router = APIRouter()

@router.get("/")
def get_repertoire(db: Session = Depends(get_db)):
    data = crud.get_full_repertoire(db)
    return data

@router.put("/{date_str}")
def update_repertoire(date_str: str, req: schemas.RepertoireUpdateRequest, changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        crud.update_repertoire_for_date(db, date_str, req.songs)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{date_str}/{song_name}")
def delete_song_from_repertoire(date_str: str, song_name: str, changer: str = Query(...), pin: str = Query(...), db: Session = Depends(get_db)):
    if not crud.verify_pin(db, changer, pin) or not crud.is_admin(db, changer):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        data = crud.get_full_repertoire(db)
        if date_str not in data:
            raise HTTPException(status_code=404, detail="Date not found")
        songs = data[date_str]["songs"]
        if song_name not in [s["name"] for s in songs]:
            raise HTTPException(status_code=404, detail="Song not found in repertoire")
        new_songs = [s["name"] for s in songs if s["name"] != song_name]
        crud.update_repertoire_for_date(db, date_str, new_songs)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))