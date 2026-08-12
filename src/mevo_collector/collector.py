"""In-memory collection of MEVO feed snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Iterable
from typing import Any

from .api import ApiError, JsonResponse, MevoApi


FEED_RECORD_KEYS: dict[str, str] = {
    "station_status": "stations",
    "free_bike_status": "bikes",
    "station_information": "stations",
    "vehicle_types": "vehicle_types",
}
DEFAULT_FEEDS = ("station_status", "free_bike_status")


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
        key = FEED_RECORD_KEYS[self.feed_name]
        return self.parsed["data"][key]


@dataclass
class CollectionResult:
    collected_at: datetime
    feeds: dict[str, FeedSnapshot]
    errors: dict[str, str]

    @property
    def partial_failure(self) -> bool:
        return bool(self.feeds) and bool(self.errors)

    @property
    def total_failure(self) -> bool:
        return not self.feeds and bool(self.errors)


def _validate_feed(response: JsonResponse, feed_name: str) -> None:
    data = response.payload.get("data")
    key = FEED_RECORD_KEYS[feed_name]
    if not isinstance(data, dict) or key not in data:
        raise ApiError(f"{feed_name} response has no data.{key} collection")
    if not isinstance(data[key], list):
        raise ApiError(f"{feed_name} data.{key} collection is not a list")
    if not all(isinstance(record, dict) for record in data[key]):
        raise ApiError(f"{feed_name} data.{key} contains a non-object record")


def collect_snapshot(
    api: MevoApi | None = None,
    feed_names: Iterable[str] | None = None,
) -> CollectionResult:
    """Fetch selected feeds, retaining successful feeds after partial failure."""
    client = api or MevoApi()
    collected_at = datetime.now(timezone.utc)
    discovery = client.get_discovery().payload
    feeds: dict[str, FeedSnapshot] = {}
    errors: dict[str, str] = {}
    selected_feeds = tuple(feed_names) if feed_names is not None else DEFAULT_FEEDS
    for feed_name in selected_feeds:
        try:
            if feed_name not in FEED_RECORD_KEYS:
                raise ValueError(f"Unsupported feed: {feed_name}")
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
        except ApiError as exc:  # isolate expected API/validation failures only
            errors[feed_name] = str(exc)
    return CollectionResult(collected_at=collected_at, feeds=feeds, errors=errors)
