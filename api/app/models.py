from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    pin_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    duty_assignments = relationship("DutyAssignment", back_populates="user")


class DutyDate(Base):
    __tablename__ = "duty_dates"
    id = Column(Integer, primary_key=True)
    date_str = Column(String(20), unique=True, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    assignments = relationship("DutyAssignment", back_populates="date")
    repertoire = relationship("Repertoire", back_populates="date")
    colors = relationship("DateColor", back_populates="date")


class DutyAssignment(Base):
    __tablename__ = "duty_assignments"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    date = relationship("DutyDate", back_populates="assignments")
    user = relationship("User", back_populates="duty_assignments")
    __table_args__ = (UniqueConstraint("date_id", "user_id", name="uq_date_user"),)


class Song(Base):
    __tablename__ = "songs"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    text = Column(Text, nullable=True)
    repertoire = relationship("Repertoire", back_populates="song")   # <-- добавлено


class Repertoire(Base):
    __tablename__ = "repertoire"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"))
    position = Column(Integer, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    date = relationship("DutyDate", back_populates="repertoire")
    song = relationship("Song", back_populates="repertoire")
    __table_args__ = (UniqueConstraint("date_id", "song_id", name="uq_date_song"),)


class DateColor(Base):
    __tablename__ = "date_colors"
    id = Column(Integer, primary_key=True)
    date_id = Column(Integer, ForeignKey("duty_dates.id", ondelete="CASCADE"))
    color = Column(String(50))
    date = relationship("DutyDate", back_populates="colors")
    __table_args__ = (UniqueConstraint("date_id", "color", name="uq_date_color"),)


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"
    key = Column(String(50), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())