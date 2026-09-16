import redis
import logging

from redis.exceptions import RedisError

from .config import settings
from .logging_config import log_dependency_warning
from .metrics import record_rate_limit

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    health_check_interval=30,
    socket_connect_timeout=2,
    socket_timeout=2,
)

logger = logging.getLogger(__name__)

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def check_rate_limit(
    user_id: int, action: str = "checkin", max_attempts: int = 10, window_seconds: int = 60
) -> bool:
    """Returns True if the request is allowed, False if the user should back off.

    Simple fixed-window counter, not a lock. Good enough to stop a client from
    hammering the check-in button.
    """
    if user_id <= 0 or max_attempts <= 0 or window_seconds <= 0:
        raise ValueError("rate-limit arguments must be positive")
    if not action or not action.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid rate-limit action")
    key = f"ratelimit:{action}:{user_id}"
    try:
        current = redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds)
    except RedisError:
        # Availability is preferable to turning an optional abuse control into
        # a check-in outage. Authentication/database constraints remain active.
        log_dependency_warning(
            logger,
            "rate_limiter_degraded",
            dependency="redis",
            operation="rate_limit",
        )
        record_rate_limit("fail_open")
        return True
    allowed = int(current) <= max_attempts
    record_rate_limit("allowed" if allowed else "limited")
    return allowed
