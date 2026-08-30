from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    pin_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")


class DutyDate(Base):
    __tablename__ = "duty_dates"
    id = Column(Integer, primary_key=True)
    date_str = Column(String(20), unique=True, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class DutyAssignment(Base):
    __tablename__ = "duty_assignments"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("date_id", "user_id", name="uq_date_user"),)


class Song(Base):
    __tablename__ = "songs"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    text = Column(Text, nullable=True)


class Repertoire(Base):
    __tablename__ = "repertoire"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"))
    position = Column(Integer, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("date_id", "song_id", name="uq_date_song"),)


class DateColor(Base):
    __tablename__ = "date_colors"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    color = Column(String(50))
    __table_args__ = (UniqueConstraint("date_id", "color", name="uq_date_color"),)


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"
    key = Column(String(50), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())