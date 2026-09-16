from app import habits


def test_schema_invalid_cache_entry_is_evicted_and_missed(monkeypatch):
    deleted: list[str] = []
    monkeypatch.setattr(habits.cache, "get_json", lambda key: [{"id": "not-an-integer"}])
    monkeypatch.setattr(habits.cache, "delete_keys", lambda *keys: deleted.extend(keys) or True)

    assert habits._validated_cache_hit("habit-cache-key", habits._HABITS_ADAPTER) is None
    assert deleted == ["habit-cache-key"]


def test_schema_valid_cache_entry_is_returned_unchanged(monkeypatch):
    cached = {
        "id": 4,
        "user_id": 2,
        "name": "Read",
        "created_at": "2026-09-12T10:30:00",
        "current_streak": 3,
        "longest_streak": 7,
        "completed_today": True,
        "checkins": [],
    }
    monkeypatch.setattr(habits.cache, "get_json", lambda key: cached)

    assert habits._validated_cache_hit("habit-cache-key", habits._HABIT_ADAPTER) is cached
