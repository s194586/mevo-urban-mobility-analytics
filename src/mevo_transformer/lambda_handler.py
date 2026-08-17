"""AWS Lambda entry point for daily cleaned MEVO batches."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .daily_job import run_daily_batch

DEFAULT_TIMEZONE = "Europe/Warsaw"
TRANSFORM_FEEDS = ("station_status", "station_information")
_ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def previous_local_date(
    now_utc: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> date:
    """Return the previous calendar day in the requested local timezone."""

    if not isinstance(now_utc, datetime):
        raise TypeError("now_utc must be a datetime")
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")

    try:
        timezone = ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"invalid timezone: {timezone_name!r}") from exc

    return now_utc.astimezone(timezone).date() - timedelta(days=1)


def _manual_local_date(event: Any) -> date | None:
    if not isinstance(event, dict) or "local_date" not in event:
        return None

    value = event["local_date"]
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValueError("local_date must be in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("local_date must be a valid date in YYYY-MM-DD format") from exc


def _job_result(result: Any) -> dict[str, Any]:
    """Convert one DailyJobResult into a JSON-serializable response item."""

    cleaned_object = result.cleaned_object
    return {
        "feed_name": result.feed_name,
        "snapshot_count": result.snapshot_count,
        "row_count": result.row_count,
        "warning_count": result.warning_count,
        "bucket": cleaned_object.bucket,
        "key": cleaned_object.key,
    }


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Create cleaned Parquet batches for both MEVO feeds for one local day."""

    del context
    manual_date = _manual_local_date(event)
    local_date = (
        manual_date
        if manual_date is not None
        else previous_local_date(datetime.now(UTC), DEFAULT_TIMEZONE)
    )

    bucket = os.environ.get("MEVO_RAW_BUCKET")
    if not bucket:
        raise RuntimeError("Missing required environment variable: MEVO_RAW_BUCKET")

    feeds = []
    for feed_name in TRANSFORM_FEEDS:
        result = run_daily_batch(bucket, feed_name, local_date)
        feeds.append(_job_result(result))

    return {
        "status": "ok",
        "local_date": local_date.isoformat(),
        "timezone": DEFAULT_TIMEZONE,
        "feeds": feeds,
    }
