import gzip
import json
import unittest
from datetime import UTC, datetime

from mevo_transformer import RawSnapshot, RawSnapshotReadError, read_raw_snapshot


TIMESTAMP = "2026-08-12T12-18-08.484729Z"
KEY = f"raw/station_status/year=2026/month=08/day=12/{TIMESTAMP}.json.gz"


def compressed(payload):
    return gzip.compress(json.dumps(payload).encode("utf-8"))


class RawReaderTests(unittest.TestCase):
    def test_reads_snapshot_and_preserves_payload(self):
        payload = {"data": [{"station_id": "A", "num_bikes_available": 3}]}
        result = read_raw_snapshot(compressed(payload), KEY)

        self.assertEqual(
            result,
            RawSnapshot(
                feed_name="station_status",
                snapshot_ts=datetime(2026, 8, 12, 12, 18, 8, 484729, tzinfo=UTC),
                payload=payload,
                object_key=KEY,
            ),
        )
        self.assertIs(result.snapshot_ts.tzinfo, UTC)
        self.assertEqual(result.payload, payload)

    def test_supports_any_feed_name(self):
        for feed_name in ["station_status", "station_information", "vehicle_types"]:
            with self.subTest(feed_name=feed_name):
                key = KEY.replace("station_status", feed_name)
                self.assertEqual(
                    read_raw_snapshot(compressed({"feed": feed_name}), key).feed_name,
                    feed_name,
                )

    def test_invalid_payload_raises(self):
        cases = [
            (b"not gzip", "gzip"),
            (gzip.compress(b"{not json}"), "JSON"),
            (gzip.compress(b"\xff"), "UTF-8"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(RawSnapshotReadError) as raised:
                    read_raw_snapshot(payload, KEY)
                self.assertIn(expected, str(raised.exception))

    def test_invalid_key_raises(self):
        keys = [
            KEY.replace(TIMESTAMP, "2026-08-12T12-18-08Z"),
            KEY.replace(".json.gz", ".json"),
            "raw/station_status/year=2026/month=08/day=12/",
            KEY.replace("station_status", ""),
            KEY.replace("year=2026", "year=2025"),
            KEY.replace("month=08", "month=07"),
            KEY.replace("day=12", "day=11"),
        ]
        for key in keys:
            with self.subTest(key=key):
                with self.assertRaises(RawSnapshotReadError):
                    read_raw_snapshot(compressed({"ok": True}), key)

    def test_valid_json_non_dict_is_returned_without_feed_validation(self):
        payload = [1, "hello", None]
        self.assertEqual(read_raw_snapshot(compressed(payload), KEY).payload, payload)

    def test_reader_does_not_mutate_payload(self):
        payload = {"items": [{"id": 1}], "last_updated": 123}
        before = {"items": [{"id": 1}], "last_updated": 123}
        read_raw_snapshot(compressed(payload), KEY)
        self.assertEqual(payload, before)

    def test_compressed_bytes_must_be_bytes_like(self):
        for value in [None, "gzip", 123]:
            with self.subTest(value=value):
                with self.assertRaises(RawSnapshotReadError):
                    read_raw_snapshot(value, KEY)

    def test_reads_bytearray(self):
        payload = {"feed": "station_status"}
        self.assertEqual(
            read_raw_snapshot(bytearray(compressed(payload)), KEY).payload,
            payload,
        )

    def test_reads_memoryview(self):
        payload = {"feed": "station_status"}
        self.assertEqual(
            read_raw_snapshot(memoryview(compressed(payload)), KEY).payload,
            payload,
        )

    def test_object_key_must_be_string(self):
        for key in [None, 123]:
            with self.subTest(key=key):
                with self.assertRaises(RawSnapshotReadError):
                    read_raw_snapshot(compressed({}), key)


if __name__ == "__main__":
    unittest.main()
