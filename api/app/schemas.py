from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, field_serializer
from typing import List, Optional, Dict


# ----- Users -----
class UserBase(BaseModel):
    name: str


class UserCreate(UserBase):
    pin: str


class UserResponse(UserBase):
    id: int
    role: str

    # В Pydantic V2 вместо orm_mode используется from_attributes
    model_config = ConfigDict(from_attributes=True)


# ----- Duty -----
class DutyDateBase(BaseModel):
    date_str: str


class DutyDateResponse(DutyDateBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class DutyAssignmentBase(BaseModel):
    user_id: int
    date_id: int


class DutyToggleRequest(BaseModel):
    date_str: str
    user_name: str
    value: bool


class DutyDateCreateRequest(BaseModel):
    # Свободный формат: "10.10.2026" или "10.10.2026 (утро 10-12)"
    date_str: str


class DutyDateRenameRequest(BaseModel):
    # Новая дата в том же формате, что и при создании.
    new_date_str: str


class DutyMatrixResponse(BaseModel):
    dates: List[str]
    names: List[str]
    matrix: List[List[bool]]


# ----- Songs -----
class SongBase(BaseModel):
    name: str
    text: Optional[str] = None


class SongCreate(SongBase):
    pass


class SongResponse(SongBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SongTextUpdateRequest(BaseModel):
    # Текст песни приходит в теле: в query он упирается в лимит длины URL.
    text: str


# ----- Repertoire -----
class RepertoireItem(BaseModel):
    song_name: str
    position: int


class RepertoireDateResponse(BaseModel):
    date: str
    songs: List[RepertoireItem]
    colors: List[str]


class RepertoireUpdateRequest(BaseModel):
    songs: List[str]


class RepertoireFullResponse(BaseModel):
    dates: Dict[str, RepertoireDateResponse]


# ----- Auth -----
class LoginRequest(BaseModel):
    name: str
    pin: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    role: Optional[str] = None


class UserCreateRequest(UserCreate):
    """Создание пользователя админом: PIN и роль приходят в теле, не в URL."""

    role: str = "user"


class UserPinUpdateRequest(BaseModel):
    # Новый PIN — только в теле запроса: в query string он попал бы в логи.
    new_pin: str


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserNamesResponse(BaseModel):
    names: List[str]


class UsersListResponse(BaseModel):
    users: List[UserResponse]


# ----- Sync history -----
class SyncHistoryResponse(BaseModel):
    """
    Метки времени в БД хранятся в UTC (контейнер Postgres без TZ => now() в UTC).
    Отдаём их с явным смещением (+00:00) — браузер сам переведёт в часовой пояс пользователя.
    """
    id: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: Optional[str] = None
    details: Optional[str] = None
    triggered_by: Optional[str] = None
    changes_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("started_at", "finished_at")
    def serialize_utc(self, value: Optional[datetime]):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
