import gzip
from datetime import UTC, datetime

import pytest

from mevo_transformer import RawSnapshot, RawSnapshotReadError, read_raw_snapshot


TIMESTAMP = "2026-08-12T12-18-08.484729Z"
KEY = f"raw/station_status/year=2026/month=08/day=12/{TIMESTAMP}.json.gz"


def compressed(payload):
    import json

    return gzip.compress(json.dumps(payload).encode("utf-8"))


def test_reads_snapshot_and_preserves_payload():
    payload = {"data": [{"station_id": "A", "num_bikes_available": 3}]}
    result = read_raw_snapshot(compressed(payload), KEY)

    assert result == RawSnapshot(
        feed_name="station_status",
        snapshot_ts=datetime(2026, 8, 12, 12, 18, 8, 484729, tzinfo=UTC),
        payload=payload,
        object_key=KEY,
    )
    assert result.snapshot_ts.tzinfo is UTC
    assert result.payload == payload


@pytest.mark.parametrize("feed_name", ["station_status", "station_information", "vehicle_types"])
def test_supports_any_feed_name(feed_name):
    key = KEY.replace("station_status", feed_name)
    assert read_raw_snapshot(compressed({"feed": feed_name}), key).feed_name == feed_name


@pytest.mark.parametrize(
    "payload, expected",
    [
        (b"not gzip", "gzip"),
        (gzip.compress(b"{not json}"), "JSON"),
        (gzip.compress(b"\xff"), "UTF-8"),
    ],
)
def test_invalid_payload_raises(payload, expected):
    with pytest.raises(RawSnapshotReadError, match=expected):
        read_raw_snapshot(payload, KEY)


@pytest.mark.parametrize(
    "key",
    [
        KEY.replace(TIMESTAMP, "2026-08-12T12-18-08Z"),
        KEY.replace(".json.gz", ".json"),
        "raw/station_status/year=2026/month=08/day=12/",
        KEY.replace("station_status", ""),
        KEY.replace("year=2026", "year=2025"),
        KEY.replace("month=08", "month=07"),
        KEY.replace("day=12", "day=11"),
    ],
)
def test_invalid_key_raises(key):
    with pytest.raises(RawSnapshotReadError):
        read_raw_snapshot(compressed({"ok": True}), key)


def test_valid_json_non_dict_is_returned_without_feed_validation():
    payload = [1, "hello", None]
    assert read_raw_snapshot(compressed(payload), KEY).payload == payload


def test_reader_does_not_mutate_payload():
    payload = {"items": [{"id": 1}], "last_updated": 123}
    before = {"items": [{"id": 1}], "last_updated": 123}
    read_raw_snapshot(compressed(payload), KEY)
    assert payload == before


@pytest.mark.parametrize("value", [None, "gzip", 123])
def test_compressed_bytes_must_be_bytes_like(value):
    with pytest.raises(RawSnapshotReadError):
        read_raw_snapshot(value, KEY)


@pytest.mark.parametrize("key", [None, 123])
def test_object_key_must_be_string(key):
    with pytest.raises(RawSnapshotReadError):
        read_raw_snapshot(compressed({}), key)
