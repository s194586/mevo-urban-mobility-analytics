"""Read and validate immutable compressed RAW snapshots."""

from __future__ import annotations

import gzip
import json
import re
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class RawSnapshotReadError(ValueError):
    """Raised when a RAW snapshot cannot be read or its key is invalid."""


@dataclass(frozen=True)
class RawSnapshot:
    """A decoded RAW snapshot and the metadata encoded in its S3 key."""

    feed_name: str
    snapshot_ts: datetime
    payload: Any
    object_key: str


_OBJECT_KEY_RE = re.compile(
    r"^raw/(?P<feed_name>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/day=(?P<day>\d{2})/"
    r"(?P<filename>[^/]+)$"
)
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S.%fZ"
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{6}Z$")


def read_raw_snapshot(
    compressed_bytes: bytes | bytearray | memoryview, object_key: str
) -> RawSnapshot:
    """Decode a gzip-compressed JSON RAW snapshot from bytes.

    The feed contract is intentionally not validated here; syntactically valid
    JSON of any type is returned unchanged as ``payload``.
    """

    if not isinstance(compressed_bytes, (bytes, bytearray, memoryview)):
        raise RawSnapshotReadError("compressed_bytes must be bytes-like")
    if not isinstance(object_key, str):
        raise RawSnapshotReadError("object_key must be a string")

    match = _OBJECT_KEY_RE.fullmatch(object_key)
    if match is None:
        raise RawSnapshotReadError("object_key does not match the RAW key structure")

    filename = match.group("filename")
    if not filename.endswith(".json.gz"):
        raise RawSnapshotReadError("RAW object filename must end with .json.gz")

    timestamp_text = filename[: -len(".json.gz")]
    if _TIMESTAMP_RE.fullmatch(timestamp_text) is None:
        raise RawSnapshotReadError("snapshot timestamp has an invalid format")
    try:
        snapshot_ts = datetime.strptime(timestamp_text, _TIMESTAMP_FORMAT).replace(
            tzinfo=UTC
        )
    except ValueError as exc:
        raise RawSnapshotReadError("snapshot timestamp is invalid") from exc

    if (
        int(match.group("year")) != snapshot_ts.year
        or int(match.group("month")) != snapshot_ts.month
        or int(match.group("day")) != snapshot_ts.day
    ):
        raise RawSnapshotReadError("key partition does not match snapshot timestamp")

    try:
        decoded = gzip.decompress(compressed_bytes).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError, zlib.error) as exc:
        raise RawSnapshotReadError("RAW payload is not valid gzip or UTF-8") from exc
    try:
        payload = json.loads(decoded)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RawSnapshotReadError("RAW payload is not valid JSON") from exc

    return RawSnapshot(
        feed_name=match.group("feed_name"),
        snapshot_ts=snapshot_ts,
        payload=payload,
        object_key=object_key,
    )
