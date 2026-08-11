"""In-memory collection of one MEVO dynamic snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .api import ApiError, JsonResponse, MevoApi


@dataclass(frozen=True)
class FeedSnapshot:
    feed_name: str
    source_url: str
    collected_at: datetime
    source_last_updated: int | None
    raw_bytes: bytes
    parsed: dict[str, Any]

    @property
    def records(self) -> list[dict[str, Any]]:
        key = "stations" if self.feed_name == "station_status" else "bikes"
        return self.parsed["data"][key]


@dataclass
class CollectionResult:
    collected_at: datetime
    feeds: dict[str, FeedSnapshot]
    errors: dict[str, str]

    @property
    def partial_failure(self) -> bool:
        return bool(self.errors)


def _validate_feed(response: JsonResponse, feed_name: str) -> None:
    data = response.payload.get("data")
    key = "stations" if feed_name == "station_status" else "bikes"
    if not isinstance(data, dict) or key not in data:
        raise ApiError(f"{feed_name} response has no data.{key} collection")
    if not isinstance(data[key], list) or not data[key]:
        raise ApiError(f"{feed_name} data.{key} collection is empty or invalid")
    if not all(isinstance(record, dict) for record in data[key]):
        raise ApiError(f"{feed_name} data.{key} contains a non-object record")


def collect_snapshot(api: MevoApi | None = None) -> CollectionResult:
    """Fetch both dynamic feeds, retaining successful feeds after partial failure."""
    client = api or MevoApi()
    collected_at = datetime.now(timezone.utc)
    discovery = client.get_discovery().payload
    feeds: dict[str, FeedSnapshot] = {}
    errors: dict[str, str] = {}
    for feed_name in ("station_status", "free_bike_status"):
        try:
            response = client.get_feed(discovery, feed_name)
            _validate_feed(response, feed_name)
            feeds[feed_name] = FeedSnapshot(
                feed_name=feed_name,
                source_url=response.url,
                collected_at=collected_at,
                source_last_updated=response.source_last_updated,
                raw_bytes=response.raw_bytes,
                parsed=response.payload,
            )
        except Exception as exc:  # isolate one feed failure from the other
            errors[feed_name] = str(exc)
    return CollectionResult(collected_at=collected_at, feeds=feeds, errors=errors)
