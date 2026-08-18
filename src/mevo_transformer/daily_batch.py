"""In-memory daily batch orchestration for cleaned MEVO feed data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    """A compressed RAW object supplied by the storage layer."""

    object_key: str
    compressed_bytes: bytes


@dataclass(frozen=True)
class DailyBatchResult:
    """The in-memory output of one feed's daily batch."""

    feed_name: str
    local_date: date
    snapshot_count: int
    row_count: int
    parquet_bytes: bytes
    warnings: tuple[str, ...]
    timezone_name: str = "Europe/Warsaw"


def _build_daily_batch(
    raw_objects: Iterable[RawObject],
    expected_feed: str,
    local_date: date,
    timezone_name: str,
) -> DailyBatchResult:
    objects = list(raw_objects)
    if not objects:
        raise DailyBatchError(f"cannot build {expected_feed} daily batch from empty input")
    if isinstance(local_date, datetime) or not isinstance(local_date, date):
        raise DailyBatchError("local_date must be a date")
    try:
        timezone = ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise DailyBatchError(f"invalid timezone: {timezone_name!r}") from exc

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
        if snapshot.snapshot_ts.astimezone(timezone).date() != local_date:
            raise DailyBatchError(
                f"snapshot {snapshot.snapshot_ts!r} from object {raw_object.object_key} "
                f"does not belong to local date {local_date!r} in {timezone_name!r}"
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

    records.sort(key=lambda record: (record["snapshot_ts"], record["station_id"]))
    if expected_feed == "station_status":
        parquet_bytes = write_station_status_parquet(records)
    else:
        parquet_bytes = write_station_information_parquet(records)

    return DailyBatchResult(
        feed_name=expected_feed,
        local_date=local_date,
        snapshot_count=len(snapshots),
        row_count=len(records),
        parquet_bytes=parquet_bytes,
        warnings=tuple(warnings),
        timezone_name=timezone_name,
    )


def build_station_status_daily_batch(
    raw_objects: Iterable[RawObject],
    local_date: date,
    timezone_name: str = "Europe/Warsaw",
) -> DailyBatchResult:
    """Build one local-day station_status Parquet batch in memory."""

    return _build_daily_batch(raw_objects, "station_status", local_date, timezone_name)


def build_station_information_daily_batch(
    raw_objects: Iterable[RawObject],
    local_date: date,
    timezone_name: str = "Europe/Warsaw",
) -> DailyBatchResult:
    """Build one local-day station_information Parquet batch in memory."""

    return _build_daily_batch(raw_objects, "station_information", local_date, timezone_name)
