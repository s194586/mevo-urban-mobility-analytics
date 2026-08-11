"""Small HTTP client for the public MEVO GBFS API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GBFS_URL = "https://gbfs.urbansharing.com/rowermevo.pl/gbfs.json"
CLIENT_IDENTIFIER = "maciej-mevo-analytics"


class ApiError(RuntimeError):
    """Raised when MEVO cannot provide a valid JSON response."""


@dataclass(frozen=True)
class JsonResponse:
    url: str
    raw_bytes: bytes
    payload: dict[str, Any]

    @property
    def source_last_updated(self) -> int | None:
        value = self.payload.get("last_updated")
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class MevoApi:
    """HTTP access and GBFS auto-discovery, without storage concerns."""

    def __init__(
        self,
        *,
        base_url: str = GBFS_URL,
        client_identifier: str = CLIENT_IDENTIFIER,
        timeout: float = 10.0,
        retries: int = 2,
        backoff: float = 0.2,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = base_url
        self.client_identifier = client_identifier
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.opener = opener

    def get_json(self, url: str) -> JsonResponse:
        request = Request(
            url,
            headers={"Client-Identifier": self.client_identifier, "Accept": "application/json"},
            method="GET",
        )
        attempts = self.retries + 1
        for attempt in range(attempts):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", response.getcode())
                    raw_bytes = response.read()
                if status < 200 or status >= 300:
                    raise ApiError(f"HTTP {status} from {url}")
                try:
                    payload = json.loads(raw_bytes)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ApiError(f"Invalid JSON from {url}") from exc
                if not isinstance(payload, dict):
                    raise ApiError(f"JSON response from {url} is not an object")
                return JsonResponse(url=url, raw_bytes=raw_bytes, payload=payload)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise ApiError(f"HTTP {exc.code} from {url}") from exc
            except (TimeoutError, URLError, OSError) as exc:
                if attempt == attempts - 1:
                    raise ApiError(f"Request failed for {url}: {exc}") from exc
            time.sleep(self.backoff * (attempt + 1))
        raise AssertionError("unreachable")

    def get_discovery(self) -> JsonResponse:
        return self.get_json(self.base_url)

    def feed_url(self, discovery: dict[str, Any], feed_name: str) -> str:
        """Return a feed URL from GBFS 2.x discovery data, independent of language."""
        data = discovery.get("data")
        candidates: list[dict[str, Any]] = []
        if isinstance(data, dict):
            if isinstance(data.get("feeds"), list):
                candidates.extend(data["feeds"])
            for language_data in data.values():
                if isinstance(language_data, dict) and isinstance(language_data.get("feeds"), list):
                    candidates.extend(language_data["feeds"])
        if isinstance(discovery.get("feeds"), list):
            candidates.extend(discovery["feeds"])
        for feed in candidates:
            if isinstance(feed, dict) and feed.get("name") == feed_name and isinstance(feed.get("url"), str):
                return feed["url"]
        raise ApiError(f"Feed {feed_name!r} not found in GBFS discovery")

    def get_feed(self, discovery: dict[str, Any], feed_name: str) -> JsonResponse:
        return self.get_json(self.feed_url(discovery, feed_name))
