import os
import json
import base64
import logging
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint, DateTime, func
import bcrypt

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_ENV = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

if not DATABASE_URL or not SPREADSHEET_ID:
    logger.error("Необходимо указать DATABASE_URL и SPREADSHEET_ID в .env")
    exit(1)

# ---------- Функция загрузки учетных данных ----------
def get_google_credentials():
    """
    Загружает учетные данные сервисного аккаунта из различных источников:
    1. Переменная GOOGLE_SHEETS_CREDENTIALS (JSON-строка, base64 или путь к файлу)
    2. Файл credentials.json в папке проекта
    """
    if GOOGLE_CREDENTIALS_ENV:
        # Пробуем интерпретировать как JSON
        try:
            return json.loads(GOOGLE_CREDENTIALS_ENV)
        except json.JSONDecodeError:
            pass

        # Пробуем как base64
        try:
            decoded = base64.b64decode(GOOGLE_CREDENTIALS_ENV).decode('utf-8')
            return json.loads(decoded)
        except:
            pass

        # Пробуем как путь к файлу
        if os.path.exists(GOOGLE_CREDENTIALS_ENV):
            with open(GOOGLE_CREDENTIALS_ENV, 'r') as f:
                return json.load(f)

    # Если переменная не задана или не удалось распарсить, ищем файл по умолчанию
    if os.path.exists("credentials.json"):
        with open("credentials.json", "r") as f:
            return json.load(f)

    raise Exception("Не удалось загрузить учетные данные Google Sheets. Убедитесь, что переменная GOOGLE_SHEETS_CREDENTIALS задана корректно, или положите файл credentials.json в папку проекта.")

# Получаем учетные данные
creds_dict = get_google_credentials()
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)


# Подключение к БД
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Определяем модели (повторяем структуру из бэкенда)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    pin_hash = Column(String(255), nullable=False)
    role = Column(String(20), default='user')

class DutyDate(Base):
    __tablename__ = 'duty_dates'
    id = Column(Integer, primary_key=True)
    date_str = Column(String(20), unique=True, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class DutyAssignment(Base):
    __tablename__ = 'duty_assignments'
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey('duty_dates.id', ondelete='CASCADE'))
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    __table_args__ = (UniqueConstraint('date_id', 'user_id', name='uq_date_user'),)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Song(Base):
    __tablename__ = 'songs'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    text = Column(Text)

class Repertoire(Base):
    __tablename__ = 'repertoire'
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey('duty_dates.id', ondelete='CASCADE'))
    song_id = Column(Integer, ForeignKey('songs.id', ondelete='CASCADE'))
    position = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('date_id', 'song_id', name='uq_date_song'),)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class SyncMetadata(Base):
    __tablename__ = 'sync_metadata'
    key = Column(String(50), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class DateColor(Base):
    __tablename__ = 'date_colors'
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey('duty_dates.id', ondelete='CASCADE'))
    color = Column(String(50))
    __table_args__ = (UniqueConstraint('date_id', 'color', name='uq_date_color'),)

# Создаем таблицы, если их нет
Base.metadata.create_all(engine)

def hash_pin(pin):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pin.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def clear_db(db):
    # Очищаем таблицы в правильном порядке (с учетом внешних ключей)
    db.execute(text("DELETE FROM repertoire"))
    db.execute(text("DELETE FROM date_colors"))
    db.execute(text("DELETE FROM duty_assignments"))
    db.execute(text("DELETE FROM duty_dates"))
    db.execute(text("DELETE FROM songs"))
    db.execute(text("DELETE FROM users"))
    db.commit()
    logger.info("База данных очищена")

def migrate_users(db, sheet):
    logger.info("Миграция пользователей...")
    rows = sheet.get_all_values()
    if not rows or len(rows) < 2:
        logger.warning("Лист Пользователи пуст или нет данных")
        return
    headers = rows[0]
    # Определяем индексы колонок
    name_idx = 0  # по умолчанию
    pin_idx = 1   # по умолчанию
    role_idx = None
    for idx, h in enumerate(headers):
        h_lower = h.lower().strip()
        if h_lower == 'имя':
            name_idx = idx
        elif h_lower == 'pin':
            pin_idx = idx
        elif h_lower == 'роль':
            role_idx = idx

    admin_names_env = os.getenv("ADMIN_NAMES", "")
    admin_names = [name.strip() for name in admin_names_env.split(',') if name.strip()]

    for row in rows[1:]:
        name = row[name_idx].strip() if len(row) > name_idx else ''
        pin = row[pin_idx].strip() if len(row) > pin_idx else ''
        if not name:
            continue
        pin_hash = hash_pin(pin) if pin else ''
        role = 'user'
        if role_idx is not None and len(row) > role_idx:
            role_val = row[role_idx].strip().lower()
            if role_val in ('admin', 'administrator'):
                role = 'admin'
        # Если роль не указана в таблице, проверяем список из env
        if role == 'user' and name in admin_names:
            role = 'admin'
        user = User(name=name, pin_hash=pin_hash, role=role)
        db.add(user)
    db.commit()
    logger.info(f"Добавлено пользователей: {len(rows) - 1}")

def migrate_duty(db, sheet):
    logger.info("Миграция графика дежурств...")
    rows = sheet.get_all_values()
    if not rows or len(rows) < 2:
        logger.warning("Лист График пуст или нет данных")
        return
    headers = rows[0]
    user_names = [h.strip() for h in headers[1:] if h.strip()]
    users = {u.name: u.id for u in db.query(User).all()}
    for row in rows[1:]:
        date_str = row[0].strip() if row else ''
        if not date_str:
            continue
        date = db.query(DutyDate).filter_by(date_str=date_str).first()
        if not date:
            date = DutyDate(date_str=date_str)
            db.add(date)
            db.flush()
        for idx, user_name in enumerate(user_names):
            val = row[idx+1].strip().upper() if idx+1 < len(row) else ''
            if val in ['TRUE', 'TRUE', '1', 'ДА']:
                user_id = users.get(user_name)
                if user_id:
                    existing = db.query(DutyAssignment).filter_by(date_id=date.id, user_id=user_id).first()
                    if not existing:
                        assignment = DutyAssignment(date_id=date.id, user_id=user_id)
                        db.add(assignment)
    db.commit()
    logger.info("График дежурств обработан")

def migrate_songs(db, sheet):
    logger.info("Миграция песен...")
    rows = sheet.get_all_values()
    if not rows or len(rows) < 2:
        logger.warning("Лист Песни пуст или нет данных")
        return
    for row in rows[1:]:
        name = row[0].strip() if len(row) > 0 else ''
        text = row[1].strip() if len(row) > 1 else ''
        if not name:
            continue
        song = db.query(Song).filter_by(name=name).first()
        if not song:
            song = Song(name=name, text=text)
            db.add(song)
    db.commit()
    logger.info(f"Песни импортированы")

def migrate_repertoire(db, sheet):
    logger.info("Миграция репертуара...")
    rows = sheet.get_all_values()
    if not rows or len(rows) < 2:
        logger.warning("Лист репертуар пуст или нет данных")
        return
    for row in rows[1:]:
        date_str = row[0].strip() if len(row) > 0 else ''
        songs_raw = row[1].strip() if len(row) > 1 else ''
        colors_raw = row[2].strip() if len(row) > 2 else ''
        if not date_str:
            continue
        date = db.query(DutyDate).filter_by(date_str=date_str).first()
        if not date:
            date = DutyDate(date_str=date_str)
            db.add(date)
            db.flush()
        # Песни
        song_names = [s.strip() for s in songs_raw.split('\n') if s.strip()]
        for pos, name in enumerate(song_names):
            song = db.query(Song).filter_by(name=name).first()
            if song:
                existing = db.query(Repertoire).filter_by(date_id=date.id, song_id=song.id).first()
                if not existing:
                    rep = Repertoire(date_id=date.id, song_id=song.id, position=pos)
                    db.add(rep)
        # Цвета
        colors = [c.strip() for c in colors_raw.split('\n') if c.strip()]
        for color in colors:
            existing = db.query(DateColor).filter_by(date_id=date.id, color=color).first()
            if not existing:
                dc = DateColor(date_id=date.id, color=color)
                db.add(dc)
    db.commit()
    logger.info("Репертуар обработан")

def main():
    logger.info("Начинаем миграцию данных из Google Sheets в PostgreSQL")
    db = SessionLocal()
    try:
        clear_db(db)

        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        try:
            users_sheet = spreadsheet.worksheet("Пользователи")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Лист 'Пользователи' не найден")
            users_sheet = None
        try:
            duty_sheet = spreadsheet.worksheet("График")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Лист 'График' не найден")
            duty_sheet = None
        try:
            songs_sheet = spreadsheet.worksheet("Песни")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Лист 'Песни' не найден")
            songs_sheet = None
        try:
            repertoire_sheet = spreadsheet.worksheet("Репертуар")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Лист 'Репертуар' не найден")
            repertoire_sheet = None

        if users_sheet:
            migrate_users(db, users_sheet)
        if duty_sheet:
            migrate_duty(db, duty_sheet)
        if songs_sheet:
            migrate_songs(db, songs_sheet)
        if repertoire_sheet:
            migrate_repertoire(db, repertoire_sheet)

        logger.info("Миграция завершена успешно")
    except Exception as e:
        logger.error(f"Ошибка миграции: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()