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


class DailyJobError(ValueError):
    """Raised when daily-job orchestration contracts are violated."""


@dataclass(frozen=True)
class DailyJobResult:
    """Summary of one feed's RAW-to-cleaned daily job."""

    feed_name: str
    date: date
    snapshot_count: int
    row_count: int
    warning_count: int
    cleaned_object: StoredCleanedObject


_BUILDERS: dict[str, Callable[[list[Any]], DailyBatchResult]] = {
    "station_status": build_station_status_daily_batch,
    "station_information": build_station_information_daily_batch,
}


def run_daily_batch(
    bucket_name: str,
    feed_name: str,
    batch_date: date,
    s3_client: Any | None = None,
) -> DailyJobResult:
    """Load, transform, and store one feed for one UTC calendar day."""

    try:
        builder = _BUILDERS[feed_name]
    except KeyError as exc:
        raise DailyJobError(f"unsupported feed: {feed_name!r}") from exc

    storage = S3BatchStorage(bucket_name, s3_client)
    raw_objects = storage.load_raw_objects(feed_name, batch_date)
    batch = builder(raw_objects)

    if batch.feed_name != feed_name:
        raise DailyJobError(
            f"daily batch feed mismatch: expected {feed_name!r}, got {batch.feed_name!r}"
        )
    if batch.date != batch_date:
        raise DailyJobError(
            f"daily batch date mismatch: expected {batch_date!r}, got {batch.date!r}"
        )

    stored = storage.store_daily_batch(batch)
    return DailyJobResult(
        feed_name=batch.feed_name,
        date=batch.date,
        snapshot_count=batch.snapshot_count,
        row_count=batch.row_count,
        warning_count=len(batch.warnings),
        cleaned_object=stored,
    )
