from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    onboarding_completed_at = Column(DateTime, nullable=True)
    onboarding_version = Column(Integer, nullable=False, default=0)

    habits = relationship("Habit", back_populates="user")


class Habit(Base):
    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    current_streak = Column(Integer, nullable=False, default=0)
    longest_streak = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="habits")
    checkins = relationship(
        "Checkin", back_populates="habit", cascade="all, delete-orphan"
    )


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("habit_id", "checked_on", name="uq_checkins_habit_checked_on"),
    )

    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(
        Integer, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checked_at = Column(DateTime, nullable=False)
    # Deliberately no Python default: callers must choose the UTC product day
    # explicitly so historical/backfilled check-ins cannot silently become today.
    checked_on = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    habit = relationship("Habit", back_populates="checkins")
