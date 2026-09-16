from datetime import date, datetime
from typing import List

from pydantic import BaseModel, Field, field_validator


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    onboarding_completed_at: datetime | None = None
    onboarding_version: int = 0

    class Config:
        from_attributes = True


class CheckinOut(BaseModel):
    id: int
    habit_id: int
    checked_at: datetime
    checked_on: date

    class Config:
        from_attributes = True


class HabitOut(BaseModel):
    id: int
    user_id: int
    name: str
    created_at: datetime
    current_streak: int
    longest_streak: int
    completed_today: bool = False
    checkins: List[CheckinOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Habit name cannot be blank")
        return normalized


class HabitUpdate(HabitCreate):
    pass


class OnboardingComplete(BaseModel):
    # PostgreSQL INTEGER is signed 32-bit. Reject out-of-range values as input
    # errors instead of surfacing a database exception as HTTP 500.
    version: int = Field(default=1, ge=1, le=2_147_483_647)
