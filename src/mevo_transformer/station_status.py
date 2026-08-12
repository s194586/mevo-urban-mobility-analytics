"""Validation and normalization for the MEVO station_status feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class StationStatusValidationError(ValueError):
    """Raised when a station_status payload violates the feed contract."""


@dataclass(frozen=True)
class StationStatusTransformResult:
    """Normalized station rows and non-fatal contract warnings."""

    records: list[dict[str, Any]]
    warnings: list[str]


def _required(mapping: dict[str, Any], key: str, location: str) -> Any:
    if key not in mapping:
        raise StationStatusValidationError(f"{location}.{key} is required")
    return mapping[key]


def _non_negative_int(value: Any, location: str) -> int:
    if type(value) is not int or value < 0:
        raise StationStatusValidationError(
            f"{location} must be a non-negative integer"
        )
    return value


def _unix_timestamp(value: Any, location: str) -> datetime:
    timestamp = _non_negative_int(value, location)
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise StationStatusValidationError(
            f"{location} is not a valid Unix timestamp"
        ) from exc


def _bool(value: Any, location: str) -> bool:
    if type(value) is not bool:
        raise StationStatusValidationError(f"{location} must be a boolean")
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


def transform_station_status(
    payload: dict[str, Any], snapshot_ts: datetime
) -> StationStatusTransformResult:
    """Validate and normalize one station_status snapshot.

    ``snapshot_ts`` is the collector capture time and is intentionally not
    derived from the feed's ``last_updated`` value.
    """
    if not isinstance(payload, dict):
        raise StationStatusValidationError("payload must be an object")
    if not isinstance(snapshot_ts, datetime) or snapshot_ts.tzinfo is None:
        raise ValueError("snapshot_ts must be a timezone-aware datetime")
    canonical_snapshot_ts = snapshot_ts.astimezone(timezone.utc)

    feed_last_updated = _unix_timestamp(
        _required(payload, "last_updated", "payload"), "payload.last_updated"
    )
    data = _required(payload, "data", "payload")
    if not isinstance(data, dict):
        raise StationStatusValidationError("payload.data must be an object")
    stations = _required(data, "stations", "payload.data")
    if not isinstance(stations, list):
        raise StationStatusValidationError("payload.data.stations must be a list")

    warnings = _warning_for_metadata(payload)
    records: list[dict[str, Any]] = []
    station_ids: set[str] = set()

    for index, station in enumerate(stations):
        location = f"payload.data.stations[{index}]"
        if not isinstance(station, dict):
            raise StationStatusValidationError(f"{location} must be an object")

        station_id = _required(station, "station_id", location)
        if not isinstance(station_id, str) or not station_id:
            raise StationStatusValidationError(
                f"{location}.station_id must be a non-empty string"
            )
        if station_id in station_ids:
            raise StationStatusValidationError(
                f"duplicate station_id {station_id!r} at {location}"
            )
        station_ids.add(station_id)

        last_reported = _unix_timestamp(
            _required(station, "last_reported", location),
            f"{location}.last_reported",
        )
        is_installed = _bool(
            _required(station, "is_installed", location), f"{location}.is_installed"
        )
        is_renting = _bool(
            _required(station, "is_renting", location), f"{location}.is_renting"
        )
        is_returning = _bool(
            _required(station, "is_returning", location), f"{location}.is_returning"
        )
        num_bikes = _non_negative_int(
            _required(station, "num_bikes_available", location),
            f"{location}.num_bikes_available",
        )
        num_docks = _non_negative_int(
            _required(station, "num_docks_available", location),
            f"{location}.num_docks_available",
        )
        num_vehicles = _non_negative_int(
            _required(station, "num_vehicles_available", location),
            f"{location}.num_vehicles_available",
        )
        if num_vehicles != num_bikes:
            warnings.append(
                f"{location}.num_vehicles_available differs from num_bikes_available"
            )

        vehicle_types = _required(station, "vehicle_types_available", location)
        if not isinstance(vehicle_types, list):
            raise StationStatusValidationError(
                f"{location}.vehicle_types_available must be a list"
            )
        counts: dict[str, int] = {}
        total_vehicle_count = 0
        has_unknown_vehicle_type = False
        for vehicle_index, vehicle in enumerate(vehicle_types):
            vehicle_location = f"{location}.vehicle_types_available[{vehicle_index}]"
            if not isinstance(vehicle, dict):
                raise StationStatusValidationError(f"{vehicle_location} must be an object")
            vehicle_id = _required(vehicle, "vehicle_type_id", vehicle_location)
            if not isinstance(vehicle_id, str) or not vehicle_id:
                raise StationStatusValidationError(
                    f"{vehicle_location}.vehicle_type_id must be a non-empty string"
                )
            if vehicle_id in counts:
                raise StationStatusValidationError(
                    f"duplicate vehicle_type_id {vehicle_id!r} at {location}"
                )
            count = _non_negative_int(
                _required(vehicle, "count", vehicle_location),
                f"{vehicle_location}.count",
            )
            counts[vehicle_id] = count
            total_vehicle_count += count
            if vehicle_id not in {"bike", "ebike"}:
                has_unknown_vehicle_type = True
                warnings.append(f"{location} contains unknown vehicle_type_id {vehicle_id!r}")

        classic = counts.get("bike", 0)
        ebikes = counts.get("ebike", 0)
        if has_unknown_vehicle_type:
            counts_match_bikes = total_vehicle_count == num_bikes
        else:
            counts_match_bikes = classic + ebikes == num_bikes
        if not counts_match_bikes:
            raise StationStatusValidationError(
                f"{location} vehicle type counts do not equal num_bikes_available"
            )

        records.append({
            "snapshot_ts": canonical_snapshot_ts,
            "feed_last_updated": feed_last_updated,
            "station_id": station_id,
            "last_reported": last_reported,
            "is_installed": is_installed,
            "is_renting": is_renting,
            "is_returning": is_returning,
            "bikes_available": num_bikes,
            "classic_bikes_available": classic,
            "ebikes_available": ebikes,
            "docks_available": num_docks,
        })

    return StationStatusTransformResult(records=records, warnings=warnings)
