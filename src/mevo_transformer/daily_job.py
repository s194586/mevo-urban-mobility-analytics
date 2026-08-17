"""Thin orchestration for one feed's cleaned daily batch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from .daily_batch import (
    DailyBatchResult,
    build_station_information_daily_batch,
    build_station_status_daily_batch,
)
from .s3_batch_storage import S3BatchStorage, StoredCleanedObject
from .time_window import local_day_utc_bounds


class DailyJobError(ValueError):
    """Raised when daily-job orchestration contracts are violated."""


@dataclass(frozen=True)
class DailyJobResult:
    """Summary of one feed's RAW-to-cleaned daily job."""

    feed_name: str
    local_date: date
    snapshot_count: int
    row_count: int
    warning_count: int
    cleaned_object: StoredCleanedObject


_BUILDERS: dict[str, Callable[[list[Any], date, str], DailyBatchResult]] = {
    "station_status": build_station_status_daily_batch,
    "station_information": build_station_information_daily_batch,
}


def run_daily_batch(
    bucket_name: str,
    feed_name: str,
    batch_date: date,
    s3_client: Any | None = None,
) -> DailyJobResult:
    """Load, transform, and store one feed for one Warsaw local day."""

    try:
        builder = _BUILDERS[feed_name]
    except KeyError as exc:
        raise DailyJobError(f"unsupported feed: {feed_name!r}") from exc

    storage = S3BatchStorage(bucket_name, s3_client)
    start_utc, end_utc = local_day_utc_bounds(batch_date)
    raw_objects = storage.load_raw_objects_for_window(feed_name, start_utc, end_utc)
    batch = builder(raw_objects, batch_date)

    if batch.feed_name != feed_name:
        raise DailyJobError(
            f"daily batch feed mismatch: expected {feed_name!r}, got {batch.feed_name!r}"
        )
    if batch.local_date != batch_date:
        raise DailyJobError(
            f"daily batch local date mismatch: expected {batch_date!r}, "
            f"got {batch.local_date!r}"
        )

    stored = storage.store_daily_batch(batch)
    return DailyJobResult(
        feed_name=batch.feed_name,
        local_date=batch.local_date,
        snapshot_count=batch.snapshot_count,
        row_count=batch.row_count,
        warning_count=len(batch.warnings),
        cleaned_object=stored,
    )
