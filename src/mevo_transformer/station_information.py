"""Validation and normalization for the MEVO station_information feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any


class StationInformationValidationError(ValueError):
    """Raised when a station_information payload violates the feed contract."""


@dataclass(frozen=True)
class StationInformationTransformResult:
    """Normalized station reference rows and non-fatal contract warnings."""

    records: list[dict[str, Any]]
    warnings: list[str]


def _required(mapping: dict[str, Any], key: str, location: str) -> Any:
    if key not in mapping:
        raise StationInformationValidationError(f"{location}.{key} is required")
    return mapping[key]


def _non_negative_int(value: Any, location: str) -> int:
    if type(value) is not int or value < 0:
        raise StationInformationValidationError(
            f"{location} must be a non-negative integer"
        )
    return value


def _unix_timestamp(value: Any, location: str) -> datetime:
    timestamp = _non_negative_int(value, location)
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise StationInformationValidationError(
            f"{location} is not a valid Unix timestamp"
        ) from exc


def _number_in_range(value: Any, location: str, minimum: float, maximum: float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StationInformationValidationError(f"{location} must be a number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise StationInformationValidationError(
            f"{location} must be finite and between {minimum} and {maximum}"
        )
    return value


def _non_empty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StationInformationValidationError(
            f"{location} must be a non-empty string"
        )
    return value


def _optional_string(mapping: dict[str, Any], key: str, location: str) -> str | None:
    value = mapping.get(key)
    if value is not None and not isinstance(value, str):
        raise StationInformationValidationError(f"{location}.{key} must be a string or null")
    return value


def _warning_for_metadata(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if payload.get("version") != "2.3" and "version" in payload:
        warnings.append("top-level version is not 2.3")
    if "ttl" not in payload:
        warnings.append("top-level ttl is missing")
    elif type(payload["ttl"]) is not int or payload["ttl"] < 0 or payload["ttl"] != 15:
        warnings.append("top-level ttl is unusual")
    return warnings


def transform_station_information(
    payload: dict[str, Any], snapshot_ts: datetime
) -> StationInformationTransformResult:
    """Validate and normalize one station_information snapshot."""
    if not isinstance(payload, dict):
        raise StationInformationValidationError("payload must be an object")
    if not isinstance(snapshot_ts, datetime) or snapshot_ts.tzinfo is None:
        raise ValueError("snapshot_ts must be a timezone-aware datetime")
    canonical_snapshot_ts = snapshot_ts.astimezone(timezone.utc)

    feed_last_updated = _unix_timestamp(
        _required(payload, "last_updated", "payload"), "payload.last_updated"
    )
    data = _required(payload, "data", "payload")
    if not isinstance(data, dict):
        raise StationInformationValidationError("payload.data must be an object")
    stations = _required(data, "stations", "payload.data")
    if not isinstance(stations, list):
        raise StationInformationValidationError("payload.data.stations must be a list")

    warnings = _warning_for_metadata(payload)
    records: list[dict[str, Any]] = []
    station_ids: set[str] = set()
    for index, station in enumerate(stations):
        location = f"payload.data.stations[{index}]"
        if not isinstance(station, dict):
            raise StationInformationValidationError(f"{location} must be an object")

        station_id = _non_empty_string(_required(station, "station_id", location), f"{location}.station_id")
        if station_id in station_ids:
            raise StationInformationValidationError(
                f"duplicate station_id {station_id!r} at {location}"
            )
        station_ids.add(station_id)
        station_name = _non_empty_string(_required(station, "name", location), f"{location}.name")
        latitude = _number_in_range(_required(station, "lat", location), f"{location}.lat", -90, 90)
        longitude = _number_in_range(_required(station, "lon", location), f"{location}.lon", -180, 180)
        capacity = _non_negative_int(_required(station, "capacity", location), f"{location}.capacity")
        is_virtual_station = _required(station, "is_virtual_station", location)
        if type(is_virtual_station) is not bool:
            raise StationInformationValidationError(
                f"{location}.is_virtual_station must be a boolean"
            )

        records.append({
            "snapshot_ts": canonical_snapshot_ts,
            "feed_last_updated": feed_last_updated,
            "station_id": station_id,
            "station_name": station_name,
            "address": _optional_string(station, "address", location),
            "cross_street": _optional_string(station, "cross_street", location),
            "latitude": latitude,
            "longitude": longitude,
            "capacity": capacity,
            "is_virtual_station": is_virtual_station,
        })

    return StationInformationTransformResult(records=records, warnings=warnings)
