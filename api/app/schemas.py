from pydantic import BaseModel, ConfigDict
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
    changer: str
    pin: str


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


class VerifyPinRequest(BaseModel):
    name: str
    pin: str


class VerifyPinResponse(BaseModel):
    success: bool


class UserNamesResponse(BaseModel):
    names: List[str]


class UsersListResponse(BaseModel):
    users: List[UserResponse]