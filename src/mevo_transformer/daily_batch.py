"""In-memory daily batch orchestration for cleaned MEVO feed data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .parquet_writer import (
    write_station_information_parquet,
    write_station_status_parquet,
)
from .raw_reader import read_raw_snapshot
from .station_information import transform_station_information
from .station_status import transform_station_status


class DailyBatchError(ValueError):
    """Raised when RAW objects cannot form a valid single-feed daily batch."""


@dataclass(frozen=True)
class RawObject:
    """A compressed RAW object supplied by a future storage layer."""

    object_key: str
    compressed_bytes: bytes


@dataclass(frozen=True)
class DailyBatchResult:
    """The in-memory output of one feed's daily batch."""

    feed_name: str
    date: date
    snapshot_count: int
    row_count: int
    parquet_bytes: bytes
    warnings: list[str]


def _build_daily_batch(raw_objects: Iterable[RawObject], expected_feed: str) -> DailyBatchResult:
    objects = list(raw_objects)
    if not objects:
        raise DailyBatchError(f"cannot build {expected_feed} daily batch from empty input")

    object_keys: set[str] = set()
    for raw_object in objects:
        if not isinstance(raw_object, RawObject):
            raise DailyBatchError("raw_objects must contain RawObject instances")
        if raw_object.object_key in object_keys:
            raise DailyBatchError(f"duplicate RAW object_key: {raw_object.object_key}")
        object_keys.add(raw_object.object_key)

    snapshots = []
    records = []
    warnings: list[str] = []
    for raw_object in objects:
        snapshot = read_raw_snapshot(raw_object.compressed_bytes, raw_object.object_key)
        if snapshot.feed_name != expected_feed:
            raise DailyBatchError(
                f"expected feed {expected_feed!r}, got {snapshot.feed_name!r} "
                f"for object {raw_object.object_key}"
            )

        if expected_feed == "station_status":
            transformed = transform_station_status(snapshot.payload, snapshot.snapshot_ts)
        else:
            transformed = transform_station_information(snapshot.payload, snapshot.snapshot_ts)

        snapshots.append(snapshot)
        records.extend(transformed.records)
        warnings.extend(
            f"{raw_object.object_key}: {warning}" for warning in transformed.warnings
        )

    batch_date = snapshots[0].snapshot_ts.date()
    if any(snapshot.snapshot_ts.date() != batch_date for snapshot in snapshots[1:]):
        raise DailyBatchError("all snapshots in a daily batch must belong to one UTC date")

    records.sort(key=lambda record: (record["snapshot_ts"], record["station_id"]))
    if expected_feed == "station_status":
        parquet_bytes = write_station_status_parquet(records)
    else:
        parquet_bytes = write_station_information_parquet(records)

    return DailyBatchResult(
        feed_name=expected_feed,
        date=batch_date,
        snapshot_count=len(snapshots),
        row_count=len(records),
        parquet_bytes=parquet_bytes,
        warnings=warnings,
    )


def build_station_status_daily_batch(raw_objects: Iterable[RawObject]) -> DailyBatchResult:
    """Build one UTC-day station_status Parquet batch in memory."""

    return _build_daily_batch(raw_objects, "station_status")


def build_station_information_daily_batch(raw_objects: Iterable[RawObject]) -> DailyBatchResult:
    """Build one UTC-day station_information Parquet batch in memory."""

    return _build_daily_batch(raw_objects, "station_information")
