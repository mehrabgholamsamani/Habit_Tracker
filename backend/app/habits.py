from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from . import models, schemas
from .auth import is_production, verify_identity_token
from .cache import cache, cache_ttls
from .database import get_db
from .redis_client import check_rate_limit
from .streaks import StreakSummary, load_streak_summaries, utc_today

router = APIRouter()

_USERS_ADAPTER = TypeAdapter(list[schemas.UserOut])
_HABITS_ADAPTER = TypeAdapter(list[schemas.HabitOut])
_HABIT_ADAPTER = TypeAdapter(schemas.HabitOut)


def _requested_user_id(
    x_user_id: int | None,
    x_auth_token: str | None,
) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=400, detail="X-User-Id header is required")
    if x_user_id <= 0:
        raise HTTPException(status_code=400, detail="X-User-Id header must be a positive integer")
    verify_identity_token(x_user_id, x_auth_token)
    return x_user_id


def get_current_user_id(
    x_user_id: int | None = Header(default=None),
    x_auth_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> int:
    user_id = _requested_user_id(x_user_id, x_auth_token)
    if db.query(models.User.id).filter(models.User.id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_id


def get_users_request_user_id(
    x_user_id: int | None = Header(default=None),
    x_auth_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> int | None:
    """Keep the local user picker usable, but never expose it in production."""
    if x_user_id is None and not is_production():
        return None
    user_id = _requested_user_id(x_user_id, x_auth_token)
    if db.query(models.User.id).filter(models.User.id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_id


def _get_owned_habit(db: Session, habit_id: int, user_id: int) -> models.Habit:
    habit = (
        db.query(models.Habit)
        .options(selectinload(models.Habit.checkins))
        .filter(models.Habit.id == habit_id, models.Habit.user_id == user_id)
        .first()
    )
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return habit


def _apply_habit_summary(habit: models.Habit, summary: StreakSummary) -> None:
    habit.current_streak = summary.current
    habit.longest_streak = summary.longest
    habit.completed_today = summary.completed_today


def _load_and_apply_habit_summaries(db: Session, habits: list[models.Habit]) -> None:
    summaries = load_streak_summaries(db, [habit.id for habit in habits])
    for habit in habits:
        _apply_habit_summary(habit, summaries[habit.id])


def _habit_json(habit: models.Habit) -> dict:
    """Freeze the public response before placing it in Redis."""
    return schemas.HabitOut.model_validate(habit).model_dump(mode="json")


def _user_json(user: models.User) -> dict:
    return schemas.UserOut.model_validate(user).model_dump(mode="json")


def _validated_cache_hit(key: str, adapter: TypeAdapter):
    cached = cache.get_json(key)
    if cached is None:
        return None
    try:
        adapter.validate_python(cached)
    except ValidationError:
        cache.delete_keys(key)
        return None
    return cached


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(
    request_user_id: int | None = Depends(get_users_request_user_id),
    db: Session = Depends(get_db),
):
    if is_production():
        key, generation = cache.user_cache_key_with_generation("users", request_user_id)
    else:
        key, generation = cache.global_cache_key_with_generation("users")
    cached = _validated_cache_hit(key, _USERS_ADAPTER)
    if cached is not None:
        return cached
    query = db.query(models.User)
    if is_production():
        query = query.filter(models.User.id == request_user_id)
    users = query.order_by(models.User.id).all()
    response = [_user_json(user) for user in users]
    if is_production():
        cache.set_json_if_generation(
            key,
            response,
            user_id=request_user_id,
            generation=generation,
            ttl_seconds=cache_ttls.users,
        )
    else:
        cache.set_json_if_generation(
            key,
            response,
            namespace="users",
            generation=generation,
            ttl_seconds=cache_ttls.users,
        )
    return response


@router.patch("/users/me/onboarding", response_model=schemas.UserOut)
def complete_onboarding(
    payload: schemas.OnboardingComplete,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.onboarding_completed_at = datetime.now(timezone.utc)
    user.onboarding_version = payload.version
    db.commit()
    db.refresh(user)
    cache.invalidate_global_cache("users")
    cache.invalidate_user_cache(user_id)
    return user


@router.get("/habits", response_model=list[schemas.HabitOut])
def list_habits(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    key, generation = cache.user_cache_key_with_generation(
        "habits", user_id, resource_id=utc_today().isoformat()
    )
    cached = _validated_cache_hit(key, _HABITS_ADAPTER)
    if cached is not None:
        return cached
    habits = (
        db.query(models.Habit)
        .options(selectinload(models.Habit.checkins))
        .filter(models.Habit.user_id == user_id)
        .all()
    )
    _load_and_apply_habit_summaries(db, habits)
    response = [_habit_json(habit) for habit in habits]
    cache.set_json_if_generation(
        key,
        response,
        user_id=user_id,
        generation=generation,
        ttl_seconds=cache_ttls.habits,
    )
    return response


@router.post("/habits", response_model=schemas.HabitOut)
def create_habit(
    payload: schemas.HabitCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    habit = models.Habit(user_id=user_id, name=payload.name, current_streak=0, longest_streak=0)
    db.add(habit)
    db.commit()
    db.refresh(habit)
    cache.invalidate_user_cache(user_id)
    return habit


@router.get("/habits/{habit_id}", response_model=schemas.HabitOut)
def get_habit(
    habit_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    key, generation = cache.user_cache_key_with_generation(
        "habits", user_id, resource_id=f"{habit_id}-{utc_today().isoformat()}"
    )
    cached = _validated_cache_hit(key, _HABIT_ADAPTER)
    if cached is not None:
        return cached
    habit = _get_owned_habit(db, habit_id, user_id)
    _load_and_apply_habit_summaries(db, [habit])
    response = _habit_json(habit)
    cache.set_json_if_generation(
        key,
        response,
        user_id=user_id,
        generation=generation,
        ttl_seconds=cache_ttls.habits,
    )
    return response


@router.delete("/habits/{habit_id}", status_code=204)
def delete_habit(
    habit_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    habit = _get_owned_habit(db, habit_id, user_id)
    db.delete(habit)
    db.commit()
    cache.invalidate_user_cache(user_id)


@router.post("/habits/{habit_id}/checkins", response_model=schemas.HabitOut)
def create_checkin(
    habit_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    habit = _get_owned_habit(db, habit_id, user_id)

    if not check_rate_limit(user_id, action="checkin", max_attempts=60, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many check-in attempts, slow down")

    now = datetime.now(timezone.utc)
    db.execute(
        insert(models.Checkin)
        .values(habit_id=habit.id, checked_at=now, checked_on=now.date())
        .on_conflict_do_nothing(constraint="uq_checkins_habit_checked_on")
    )
    db.flush()
    _load_and_apply_habit_summaries(db, [habit])
    db.commit()
    db.refresh(habit)
    _load_and_apply_habit_summaries(db, [habit])
    cache.invalidate_user_cache(user_id)
    return habit


@router.delete("/habits/{habit_id}/checkins/today", response_model=schemas.HabitOut)
def delete_today_checkin(
    habit_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Undo today's check-in without affecting the habit's earlier history."""
    habit = _get_owned_habit(db, habit_id, user_id)
    db.query(models.Checkin).filter(
        models.Checkin.habit_id == habit.id,
        models.Checkin.checked_on == utc_today(),
    ).delete(synchronize_session=False)
    db.commit()
    db.expire(habit, ["checkins"])
    _load_and_apply_habit_summaries(db, [habit])
    cache.invalidate_user_cache(user_id)
    return habit


@router.patch("/habits/{habit_id}", response_model=schemas.HabitOut)
def update_habit(
    habit_id: int,
    payload: schemas.HabitUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    habit = _get_owned_habit(db, habit_id, user_id)
    habit.name = payload.name
    db.commit()
    db.refresh(habit)
    _load_and_apply_habit_summaries(db, [habit])
    cache.invalidate_user_cache(user_id)
    return habit
