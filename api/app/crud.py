import json
import bcrypt
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas

# ---------- Users ----------
def get_user_by_name(db: Session, name: str):
    return db.query(models.User).filter(models.User.name == name).first()

def verify_pin(db: Session, name: str, pin: str) -> bool:
    user = get_user_by_name(db, name)
    if not user or not user.pin_hash:
        return False
    try:
        return bcrypt.checkpw(pin.encode('utf-8'), user.pin_hash.encode('utf-8'))
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

def create_date(db: Session, date_str: str):
    """Создать новую пустую дату. Даты в графике заводятся вручную админом."""
    existing = db.query(models.DutyDate).filter(models.DutyDate.date_str == date_str).first()
    if existing:
        raise ValueError("Такая дата уже есть")
    date = models.DutyDate(date_str=date_str)
    db.add(date)
    db.commit()
    db.refresh(date)
    return date

def delete_date(db: Session, date_str: str):
    """Удалить дату вместе с дежурными, репертуаром и цветами.

    Дочерние строки чистим явно: у relationship'ов не настроен delete-cascade,
    поэтому ORM вместо удаления просто обнулил бы им date_id и оставил «сирот».
    """
    date = db.query(models.DutyDate).filter(models.DutyDate.date_str == date_str).first()
    if not date:
        raise ValueError("Дата не найдена")
    date_id = date.id
    db.query(models.DutyAssignment).filter(models.DutyAssignment.date_id == date_id).delete(synchronize_session=False)
    db.query(models.Repertoire).filter(models.Repertoire.date_id == date_id).delete(synchronize_session=False)
    db.query(models.DateColor).filter(models.DateColor.date_id == date_id).delete(synchronize_session=False)
    db.query(models.DutyDate).filter(models.DutyDate.id == date_id).delete(synchronize_session=False)
    db.commit()

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

    date.updated_at = func.now()
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
    date.updated_at = func.now()
    db.commit()

# ---------- Users (admin) ----------
def get_all_users(db: Session):
    return db.query(models.User).all()

def update_user_pin(db: Session, name: str, new_pin: str):
    user = get_user_by_name(db, name)
    if not user:
        raise ValueError("User not found")
    user.pin_hash = bcrypt.hashpw(new_pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()
    return user

def create_user(db: Session, user: schemas.UserCreate):
    existing = db.query(models.User).filter(models.User.name == user.name).first()
    if existing:
        raise ValueError("User already exists")
    hashed = bcrypt.hashpw(user.pin.encode('utf-8'), bcrypt.gensalt())
    db_user = models.User(name=user.name, pin_hash=hashed.decode('utf-8'), role='user')
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, name: str):
    user = db.query(models.User).filter(models.User.name == name).first()
    if not user:
        raise ValueError("User not found")
    # Также нужно удалить связанные назначения (каскадное удаление в БД есть)
    db.delete(user)
    db.commit()

def update_user_role(db: Session, name: str, role: str):
    user = db.query(models.User).filter(models.User.name == name).first()
    if not user:
        raise ValueError("User not found")
    user.role = role
    db.commit()
    db.refresh(user)
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
    db.query(models.Repertoire).filter(models.Repertoire.date_id == date.id).delete()
    for pos, name in enumerate(song_names):
        song = db.query(models.Song).filter(models.Song.name == name).first()
        if song:
            rep = models.Repertoire(date_id=date.id, song_id=song.id, position=pos)
            db.add(rep)
    date.updated_at = func.now()
    db.commit()

    # ---------- Sync History ----------
PENDING_CHANGES_KEY = 'pending_changes'


def _read_pending_changes(db: Session) -> list:
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == PENDING_CHANGES_KEY).first()
    if not row or not row.value:
        return []
    try:
        data = json.loads(row.value)
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def get_pending_changes(db: Session) -> list:
    """Список правок, накопившихся с прошлой синхронизации (что её вызовет)."""
    return _read_pending_changes(db)


def add_pending_change(db: Session, triggered_by: str, text: str):
    changes = _read_pending_changes(db)
    changes.append({
        "by": triggered_by or 'auto',
        "text": text,
        "at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == PENDING_CHANGES_KEY).first()
    if not row:
        row = models.SyncMetadata(key=PENDING_CHANGES_KEY, value='')
        db.add(row)
    row.value = json.dumps(changes, ensure_ascii=False)
    row.updated_at = func.now()
    db.commit()


def clear_pending_changes(db: Session):
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == PENDING_CHANGES_KEY).first()
    if row:
        row.value = '[]'
        row.updated_at = func.now()
        db.commit()


def set_force_full_sync(db: Session, value: bool = True):
    """Форсировать полную перезаливку листов на следующей синхронизации.

    Нужно при удалении даты: строки из БД исчезают, и сравнивать updated_at
    (как делает has_duty_changes) уже не с чем — иначе удаление не доедет до Sheets.
    """
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == 'force_full_sync').first()
    if not row:
        row = models.SyncMetadata(key='force_full_sync', value='')
        db.add(row)
    row.value = str(value).lower()
    row.updated_at = func.now()
    db.commit()


def set_sync_flag(db: Session, needs_sync: bool = True, triggered_by: str = 'auto', change: str = None):
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == 'sync_flag').first()
    if not row:
        row = models.SyncMetadata(key='sync_flag', value='')
        db.add(row)
    row.value = str(needs_sync)
    row.updated_at = func.now()
    db.commit()
    # Журнал правок: попадёт в историю синхронизации как «что изменилось».
    if needs_sync and change:
        add_pending_change(db, triggered_by, change)

def get_sync_flag(db: Session) -> bool:
    row = db.query(models.SyncMetadata).filter(models.SyncMetadata.key == 'sync_flag').first()
    if not row:
        return False
    return row.value.lower() == 'true'

def create_sync_history(db: Session, triggered_by: str = 'auto', changes_summary: str = None) -> int:
    history = models.SyncHistory(triggered_by=triggered_by, changes_summary=changes_summary, status='pending')
    db.add(history)
    db.commit()
    db.refresh(history)
    return history.id

def update_sync_history(db: Session, history_id: int, status: str, details: str = None):
    history = db.query(models.SyncHistory).filter(models.SyncHistory.id == history_id).first()
    if history:
        history.status = status
        history.finished_at = func.now()
        if details:
            history.details = details
        db.commit()

def get_sync_history(db: Session, limit: int = 50):
    return db.query(models.SyncHistory).order_by(models.SyncHistory.id.desc()).limit(limit).all()