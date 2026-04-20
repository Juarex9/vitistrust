from __future__ import annotations

from datetime import UTC, datetime, timedelta


ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def format_iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime(ISO_UTC_FORMAT)


def build_time_window(days_back: int = 180, end: datetime | None = None) -> tuple[str, str]:
    """Builds a UTC ISO-8601 window ending at current UTC time."""
    safe_days_back = max(1, days_back)
    end_dt = (end or datetime.now(UTC)).astimezone(UTC)
    start_dt = end_dt - timedelta(days=safe_days_back)
    return format_iso_utc(start_dt), format_iso_utc(end_dt)


def parse_iso_datetime(value: str) -> datetime:
    """Parses ISO datetime strings supporting Z suffix and timezone offsets."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("Timezone information is required in ISO datetime values")
    return parsed.astimezone(UTC)
