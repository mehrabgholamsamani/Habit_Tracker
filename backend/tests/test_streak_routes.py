from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app import habits
from app.streaks import StreakSummary


def _habit(habit_id: int = 7, user_id: int = 3):
    return SimpleNamespace(
        id=habit_id,
        user_id=user_id,
        name="Read",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        current_streak=0,
        longest_streak=0,
        completed_today=False,
        checkins=[],
    )


def test_list_habits_bulk_loads_streaks_once(monkeypatch):
    first, second = _habit(7), _habit(8)
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.all.return_value = [first, second]
    monkeypatch.setattr(habits.cache, "get_json", lambda _key: None)
    monkeypatch.setattr(habits.cache, "set_json", lambda *_args, **_kwargs: True)

    calls = []

    def load(_db, habit_ids):
        calls.append(habit_ids)
        return {
            7: StreakSummary(current=2, longest=5, completed_today=True),
            8: StreakSummary(current=0, longest=9, completed_today=False),
        }

    monkeypatch.setattr(habits, "load_streak_summaries", load)

    response = habits.list_habits(user_id=3, db=db)

    assert calls == [[7, 8]]
    assert [(item["current_streak"], item["longest_streak"], item["completed_today"]) for item in response] == [
        (2, 5, True),
        (0, 9, False),
    ]


def test_get_habit_does_not_reveal_another_users_habit(monkeypatch):
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(habits.cache, "get_json", lambda _key: None)
    loader = MagicMock()
    monkeypatch.setattr(habits, "load_streak_summaries", loader)

    with pytest.raises(HTTPException) as exc:
        habits.get_habit(habit_id=7, user_id=999, db=db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Habit not found"
    loader.assert_not_called()


def test_checkin_is_idempotent_per_calendar_day_and_invalidates_cache(monkeypatch):
    habit = _habit()
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = habit
    monkeypatch.setattr(habits, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        habits,
        "load_streak_summaries",
        lambda _db, ids: {
            ids[0]: StreakSummary(current=4, longest=6, completed_today=True)
        },
    )
    invalidated = []
    monkeypatch.setattr(
        habits.cache, "invalidate_user_cache", lambda user_id: invalidated.append(user_id) or True
    )

    response = habits.create_checkin(habit_id=7, user_id=3, db=db)

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_checkins_habit_checked_on DO NOTHING" in sql
    params = statement.compile(dialect=postgresql.dialect()).params
    assert params["checked_on"] == params["checked_at"].date()
    assert response.current_streak == 4
    assert response.longest_streak == 6
    assert response.completed_today is True
    assert invalidated == [3]
    db.commit.assert_called_once()


def test_checkin_404_happens_before_rate_limit_or_mutation(monkeypatch):
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = None
    limiter = MagicMock(return_value=True)
    monkeypatch.setattr(habits, "check_rate_limit", limiter)

    with pytest.raises(HTTPException) as exc:
        habits.create_checkin(habit_id=404, user_id=3, db=db)

    assert exc.value.status_code == 404
    limiter.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_delete_today_checkin_only_removes_current_day_and_invalidates_cache(monkeypatch):
    habit = _habit()
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = habit
    checkin_query = MagicMock()

    def query(model):
        if model is habits.models.Checkin:
            return checkin_query
        return db.query.return_value

    db.query.side_effect = query
    monkeypatch.setattr(habits, "utc_today", lambda: datetime(2026, 9, 16).date())
    monkeypatch.setattr(
        habits,
        "load_streak_summaries",
        lambda _db, ids: {
            ids[0]: StreakSummary(current=0, longest=6, completed_today=False)
        },
    )
    invalidated = []
    monkeypatch.setattr(
        habits.cache, "invalidate_user_cache", lambda user_id: invalidated.append(user_id) or True
    )

    response = habits.delete_today_checkin(habit_id=7, user_id=3, db=db)

    checkin_query.filter.assert_called_once()
    checkin_query.filter.return_value.delete.assert_called_once_with(synchronize_session=False)
    db.commit.assert_called_once()
    db.expire.assert_called_once_with(habit, ["checkins"])
    assert response.completed_today is False
    assert response.longest_streak == 6
    assert invalidated == [3]
