from sqlalchemy.orm import Session
from sqlalchemy import and_
from passlib.context import CryptContext
from . import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- Users ----------
def get_user_by_name(db: Session, name: str):
    return db.query(models.User).filter(models.User.name == name).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed = pwd_context.hash(user.pin)
    db_user = models.User(name=user.name, pin_hash=hashed)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def verify_pin(db: Session, name: str, pin: str) -> bool:
    user = get_user_by_name(db, name)
    if not user or not user.pin_hash:
        return False
    try:
        return pwd_context.verify(pin, user.pin_hash)
    except Exception:
        return False

def is_admin(db: Session, name: str) -> bool:
    user = get_user_by_name(db, name)
    if not user:
        return False
    return user.role == "admin"

# ---------- Duty Dates ----------
def get_or_create_date(db: Session, date_str: str):
    date = db.query(models.DutyDate).filter(models.DutyDate.date_str == date_str).first()
    if not date:
        date = models.DutyDate(date_str=date_str)
        db.add(date)
        db.commit()
        db.refresh(date)
    return date

def get_all_dates(db: Session):
    return db.query(models.DutyDate).order_by(models.DutyDate.date_str).all()

def toggle_duty(db: Session, date_str: str, user_name: str, value: bool):
    date = get_or_create_date(db, date_str)
    user = get_user_by_name(db, user_name)
    if not user:
        raise ValueError("User not found")
    assignment = db.query(models.DutyAssignment).filter(
        models.DutyAssignment.date_id == date.id,
        models.DutyAssignment.user_id == user.id
    ).first()
    if value:
        if not assignment:
            assignment = models.DutyAssignment(date_id=date.id, user_id=user.id)
            db.add(assignment)
    else:
        if assignment:
            db.delete(assignment)
    db.commit()
    return True

# ---------- Songs ----------
def get_all_songs(db: Session):
    return db.query(models.Song).order_by(models.Song.name).all()

def create_song(db: Session, song: schemas.SongCreate):
    db_song = models.Song(name=song.name, text=song.text)
    db.add(db_song)
    db.commit()
    db.refresh(db_song)
    return db_song

def update_song_text(db: Session, name: str, new_text: str):
    song = db.query(models.Song).filter(models.Song.name == name).first()
    if not song:
        raise ValueError("Song not found")
    song.text = new_text
    db.commit()
    return song

def delete_song(db: Session, name: str):
    song = db.query(models.Song).filter(models.Song.name == name).first()
    if not song:
        raise ValueError("Song not found")
    db.delete(song)
    db.commit()

# ---------- Repertoire ----------
def get_repertoire_for_date(db: Session, date_str: str):
    date = db.query(models.DutyDate).filter(models.DutyDate.date_str == date_str).first()
    if not date:
        return []
    return db.query(models.Repertoire).filter(models.Repertoire.date_id == date.id).order_by(models.Repertoire.position).all()

def set_repertoire_songs(db: Session, date_str: str, song_names: list):
    date = get_or_create_date(db, date_str)
    # Удаляем старые записи
    db.query(models.Repertoire).filter(models.Repertoire.date_id == date.id).delete()
    # Добавляем новые
    for pos, name in enumerate(song_names):
        song = db.query(models.Song).filter(models.Song.name == name).first()
        if song:
            rep = models.Repertoire(date_id=date.id, song_id=song.id, position=pos)
            db.add(rep)
    db.commit()

# ---------- Users (admin) ----------
def get_all_users(db: Session):
    return db.query(models.User).all()

def update_user_pin(db: Session, name: str, new_pin: str):
    user = get_user_by_name(db, name)
    if not user:
        raise ValueError("User not found")
    user.pin_hash = pwd_context.hash(new_pin)
    db.commit()
    return user

# ---------- Repertoire (full) ----------
def get_full_repertoire(db: Session):
    dates = db.query(models.DutyDate).order_by(models.DutyDate.date_str).all()
    result = {}
    for date in dates:
        repertoire_items = db.query(models.Repertoire).filter(
            models.Repertoire.date_id == date.id
        ).order_by(models.Repertoire.position).all()
        songs = []
        for item in repertoire_items:
            song = db.query(models.Song).filter(models.Song.id == item.song_id).first()
            if song:
                songs.append({
                    "name": song.name,
                    "text": song.text or ""
                })
        colors = [c.color for c in date.colors]
        result[date.date_str] = {"songs": songs, "colors": colors}
    return result

def update_repertoire_for_date(db: Session, date_str: str, song_names: list):
    date = get_or_create_date(db, date_str)
    # удаляем старые записи
    db.query(models.Repertoire).filter(models.Repertoire.date_id == date.id).delete()
    # добавляем новые
    for pos, name in enumerate(song_names):
        song = db.query(models.Song).filter(models.Song.name == name).first()
        if song:
            rep = models.Repertoire(date_id=date.id, song_id=song.id, position=pos)
            db.add(rep)
    db.commit()