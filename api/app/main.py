import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from . import models  # noqa: F401  — импорт нужен, чтобы таблицы попали в Base.metadata
from .routers import duty, songs, users, auth, repertoire, sync, sync_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём недостающие таблицы при старте.
    # Раньше create_all жил только в migrate_data.py, поэтому на пустой БД API
    # поднимался без схемы и все запросы падали с "relation does not exist".
    # create_all идемпотентен и НЕ трогает существующие таблицы: на живой базе
    # это no-op (миграций в проекте нет, схема только дополняется).
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Duty Schedule API", version="1.0.0", lifespan=lifespan)

# CORS – разрешаем запросы с фронтенда
# Фронтенд (статика) и API отдаются одним nginx на mediahlg.ru,
# поэтому запросы идут с того же origin. Список настраивается через CORS_ORIGINS.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "https://mediahlg.ru").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(duty.router, prefix="/api/duty", tags=["duty"])
app.include_router(songs.router, prefix="/api/songs", tags=["songs"])
app.include_router(repertoire.router, prefix="/api/repertoire", tags=["repertoire"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(sync_history.router, prefix="/api/sync", tags=["sync"])

@app.get("/api/health")
def health():
    return {"status": "ok"}