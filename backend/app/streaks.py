from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Streaks:
    current: int
    longest: int


@dataclass(frozen=True)
class StreakSummary:
    """The date-sensitive streak state exposed for a habit."""

    current: int
    longest: int
    completed_today: bool


def utc_today() -> date:
    """Return the current product day.

    Check-ins are recorded in UTC and the data model does not currently store a
    user timezone, so UTC is the only unambiguous date boundary.
    """
    return datetime.now(timezone.utc).date()


def calculate_streak_summary(
    completed_days: Iterable[date], today: date
) -> StreakSummary:
    """Calculate streak state from completed UTC calendar days.

    Duplicate and future dates are ignored. A run ending yesterday remains
    current because the user still has the whole of today to extend it.
    """
    days = {day for day in completed_days if day <= today}
    if not days:
        return StreakSummary(current=0, longest=0, completed_today=False)

    longest = 0
    running = 0
    previous: date | None = None
    for day in sorted(days):
        running = running + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, running)
        previous = day

    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)

    return StreakSummary(
        current=current,
        longest=longest,
        completed_today=today in days,
    )


def calculate_streaks(completed_days: Iterable[date], today: date) -> Streaks:
    """Calculate streaks from unique calendar days.

    A streak completed yesterday remains current while today is still open.
    Future completions are ignored.
    """
    summary = calculate_streak_summary(completed_days, today)
    return Streaks(current=summary.current, longest=summary.longest)


def load_streak_summaries(
    db: Session, habit_ids: Sequence[int], today: date | None = None
) -> dict[int, StreakSummary]:
    """Load lifetime streak history for many habits with one deterministic query.

    Returning entries for habits without check-ins keeps callers simple and
    avoids the list-endpoint N+1 query pattern. The unique database index on
    ``(habit_id, checked_on)`` supports both the filter and ordering. Ownership
    filtering remains the caller's responsibility; only already-authorized IDs
    should be supplied.
    """
    unique_ids = tuple(sorted(set(habit_ids)))
    if not unique_ids:
        return {}

    product_day = today or utc_today()
    # PostgreSQL computes consecutive-day islands and returns one bounded row
    # per habit. This avoids transferring an account's entire history into the
    # API process on every list/detail request.
    statement = text("""
        WITH ordered AS (
            SELECT habit_id, checked_on,
                   checked_on - (ROW_NUMBER() OVER (
                       PARTITION BY habit_id ORDER BY checked_on
                   ))::int AS run_group
            FROM checkins
            WHERE habit_id IN :habit_ids AND checked_on <= :today
        ), runs AS (
            SELECT habit_id, MIN(checked_on) AS start_day,
                   MAX(checked_on) AS end_day, COUNT(*)::int AS run_length
            FROM ordered
            GROUP BY habit_id, run_group
        )
        SELECT habit_id,
               MAX(run_length)::int AS longest,
               COALESCE(MAX(run_length) FILTER (
                   WHERE end_day IN (:today, :yesterday)
               ), 0)::int AS current,
               BOOL_OR(end_day = :today) AS completed_today
        FROM runs
        GROUP BY habit_id
    """).bindparams(bindparam("habit_ids", expanding=True))
    rows = db.execute(
        statement,
        {
            "habit_ids": unique_ids,
            "today": product_day,
            "yesterday": product_day - timedelta(days=1),
        },
    ).all()
    summaries = {
        habit_id: StreakSummary(current=0, longest=0, completed_today=False)
        for habit_id in unique_ids
    }
    for habit_id, longest, current, completed_today in rows:
        summaries[habit_id] = StreakSummary(
            current=current,
            longest=longest,
            completed_today=completed_today,
        )
    return summaries
