import os
import json
import base64
import time
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from models import User, DutyDate, DutyAssignment, Song, Repertoire, DateColor, Base, SyncMetadata, SyncHistory
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- Настройки ----------
DATABASE_URL = os.getenv("DATABASE_URL")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

if not GOOGLE_CREDENTIALS_JSON:
    try:
        with open("credentials.json", "r") as f:
            creds_dict = json.load(f)
    except FileNotFoundError:
        logger.error("No credentials provided. Set GOOGLE_SHEETS_CREDENTIALS env var or mount credentials.json")
        exit(1)
else:
    try:
        decoded = base64.b64decode(GOOGLE_CREDENTIALS_JSON).decode('utf-8')
        creds_dict = json.loads(decoded)
    except Exception:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)

# Только Sheets. Раньше здесь был auth/drive — он давал доступ ко ВСЕМУ, что
# расшарено на сервисный аккаунт, а не только к нужной таблице.
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def sync_sheet_headers(sheet, headers, start_row=1, start_col=1):
    for col, header in enumerate(headers, start=start_col):
        sheet.update_cell(start_row, col, header)


def clear_sheet(sheet):
    sheet.clear()


def sync_users(db):
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Пользователи")
    clear_sheet(sheet)
    users = db.query(User).all()
    headers = ["Имя", "PIN", "Роль"]
    sync_sheet_headers(sheet, headers)
    rows = []
    for u in users:
        rows.append([u.name, '', u.role])
    if rows:
        sheet.append_rows(rows, value_input_option='RAW', table_range='A2')
    logger.info(f"Synced {len(rows)} users")


def sync_duty(db):
    last_sync = get_last_sync_time(db, 'last_sync_duty')
    if not has_duty_changes(db, last_sync):
        logger.info("No changes in duty data, skipping sync")
        return

    logger.info("Syncing duty data...")
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("График")
    clear_sheet(sheet)
    users = db.query(User).order_by(User.name).all()
    user_names = [u.name for u in users]
    dates = db.query(DutyDate).order_by(DutyDate.date_str).all()
    headers = ["Дата"] + user_names
    sync_sheet_headers(sheet, headers)
    rows = []
    for date in dates:
        assignments = db.query(DutyAssignment).filter(DutyAssignment.date_id == date.id).all()
        assigned_user_ids = {a.user_id for a in assignments}
        row = [date.date_str]
        for u in users:
            row.append('TRUE' if u.id in assigned_user_ids else 'FALSE')
        rows.append(row)
    if rows:
        sheet.append_rows(rows, value_input_option='RAW', table_range='A2')
    set_last_sync_time(db, 'last_sync_duty')
    logger.info(f"Synced {len(rows)} duty dates")


def sync_repertoire(db):
    last_sync = get_last_sync_time(db, 'last_sync_repertoire')
    if not has_repertoire_changes(db, last_sync):
        logger.info("No changes in repertoire data, skipping sync")
        return

    logger.info("Syncing repertoire...")
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Репертуар")
    clear_sheet(sheet)
    dates = db.query(DutyDate).order_by(DutyDate.date_str).all()
    headers = ["Дата", "Песни", "Цвета"]
    sync_sheet_headers(sheet, headers)
    rows = []
    for date in dates:
        rep_items = db.query(Repertoire).filter(Repertoire.date_id == date.id).order_by(Repertoire.position).all()
        song_names = []
        for item in rep_items:
            song = db.query(Song).filter(Song.id == item.song_id).first()
            if song:
                song_names.append(song.name)
        songs_str = "\n".join(song_names)
        colors = db.query(DateColor).filter(DateColor.date_id == date.id).all()
        colors_str = "\n".join([c.color for c in colors])
        rows.append([date.date_str, songs_str, colors_str])
    if rows:
        sheet.append_rows(rows, value_input_option='RAW', table_range='A2')
    set_last_sync_time(db, 'last_sync_repertoire')
    logger.info(f"Synced {len(rows)} repertoire entries")


def get_last_sync_time(db, key='last_sync'):
    row = db.query(SyncMetadata).filter(SyncMetadata.key == key).first()
    if row:
        return row.value
    return None


def set_last_sync_time(db, key='last_sync', value=None):
    if value is None:
        value = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = db.query(SyncMetadata).filter(SyncMetadata.key == key).first()
    if row:
        row.value = value
    else:
        row = SyncMetadata(key=key, value=value)
        db.add(row)
    db.commit()


def has_duty_changes(db, last_sync):
    if not last_sync:
        return True
    count = db.query(DutyDate).filter(DutyDate.updated_at > last_sync).count()
    if count > 0:
        return True
    count = db.query(DutyAssignment).filter(DutyAssignment.updated_at > last_sync).count()
    return count > 0


def has_repertoire_changes(db, last_sync):
    if not last_sync:
        return True
    count = db.query(Repertoire).filter(Repertoire.updated_at > last_sync).count()
    if count > 0:
        return True
    count = db.query(DutyDate).filter(DutyDate.updated_at > last_sync).count()
    return count > 0


# ---------- История синхронизаций (добавлено) ----------
def create_sync_history(db, triggered_by='auto', changes_summary=None):
    history = SyncHistory(
        triggered_by=triggered_by,
        changes_summary=changes_summary,
        status='pending'
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history.id


def update_sync_history(db, history_id, status, details=None):
    history = db.query(SyncHistory).filter(SyncHistory.id == history_id).first()
    if history:
        history.status = status
        history.finished_at = datetime.now()
        if details:
            history.details = details
        db.commit()
# -------------------------------------------------


def main_sync():
    db = SessionLocal()
    try:
        flag_row = db.query(SyncMetadata).filter(SyncMetadata.key == 'sync_flag').first()
        if not flag_row or flag_row.value.lower() != 'true':
            logger.info("No sync needed")
            return

        triggered_by = 'auto'
        changes_summary = 'Scheduled sync'

        history_id = create_sync_history(db, triggered_by, changes_summary)
        try:
            sync_duty(db)
            sync_repertoire(db)
            flag_row.value = 'false'
            db.commit()
            update_sync_history(db, history_id, 'success', 'Sync completed successfully')
            logger.info("Sync completed successfully")
        except Exception as e:
            error_msg = str(e)
            db.rollback()
            update_sync_history(db, history_id, 'error', error_msg)
            logger.error(f"Sync failed: {error_msg}")
    except Exception as e:
        logger.error(f"Sync failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    while True:
        main_sync()
        time.sleep(30)