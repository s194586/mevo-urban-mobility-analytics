"""Timezone-aware analytical day boundaries."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def local_day_utc_bounds(
    local_date: date, timezone_name: str = "Europe/Warsaw"
) -> tuple[datetime, datetime]:
    """Return the UTC half-open interval for one calendar day in a timezone.

    Local midnight is calculated independently for the requested date and the
    following date, so daylight-saving transitions can produce 23- or 25-hour
    UTC intervals.
    """

    if isinstance(local_date, datetime) or not isinstance(local_date, date):
        raise TypeError("local_date must be a date")

    timezone = ZoneInfo(timezone_name)
    next_local_date = local_date + timedelta(days=1)
    start_local = datetime.combine(local_date, time.min, tzinfo=timezone)
    end_local = datetime.combine(next_local_date, time.min, tzinfo=timezone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
