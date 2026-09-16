from datetime import date, timedelta
from unittest.mock import MagicMock

from app.streaks import (
    StreakSummary,
    Streaks,
    calculate_streak_summary,
    calculate_streaks,
    load_streak_summaries,
)


TODAY = date(2026, 9, 16)


def test_empty_history_has_no_streak():
    assert calculate_streaks([], TODAY) == Streaks(current=0, longest=0)


def test_yesterdays_streak_remains_current_while_today_is_open():
    days = [TODAY - timedelta(days=offset) for offset in (1, 2, 3)]
    assert calculate_streaks(days, TODAY) == Streaks(current=3, longest=3)


def test_gap_ends_current_streak_but_preserves_longest():
    days = [
        TODAY,
        TODAY - timedelta(days=2),
        TODAY - timedelta(days=3),
        TODAY - timedelta(days=4),
    ]
    assert calculate_streaks(days, TODAY) == Streaks(current=1, longest=3)


def test_duplicates_and_future_days_do_not_change_streaks():
    days = [TODAY, TODAY, TODAY - timedelta(days=1), TODAY + timedelta(days=1)]
    assert calculate_streaks(days, TODAY) == Streaks(current=2, longest=2)


def test_streaks_are_not_artificially_capped():
    days = [TODAY - timedelta(days=offset) for offset in range(500)]
    assert calculate_streaks(days, TODAY) == Streaks(current=500, longest=500)


def test_summary_reports_completed_today_without_changing_streak_semantics():
    days = [TODAY, TODAY - timedelta(days=1)]
    assert calculate_streak_summary(days, TODAY) == StreakSummary(
        current=2,
        longest=2,
        completed_today=True,
    )


def test_summary_reports_today_open_for_a_streak_ending_yesterday():
    days = [TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert calculate_streak_summary(days, TODAY) == StreakSummary(
        current=2,
        longest=2,
        completed_today=False,
    )


def test_bulk_loader_returns_zero_summary_for_habit_without_checkins():
    db = MagicMock()
    db.execute.return_value.all.return_value = [(10, 1, 1, True)]

    summaries = load_streak_summaries(db, [10, 20], today=TODAY)

    assert summaries[10] == StreakSummary(1, 1, True)
    assert summaries[20] == StreakSummary(0, 0, False)
    db.execute.assert_called_once()
