from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import duty, songs, users, auth, repertoire
from .routers import sync

app = FastAPI(title="Duty Schedule API", version="1.0.0")

# CORS – разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # в продакшене укажите конкретный домен
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

@app.get("/api/health")
def health():
    return {"status": "ok"}