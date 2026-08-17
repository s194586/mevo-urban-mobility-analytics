import unittest
from datetime import UTC, date, datetime

from mevo_transformer import (
    DailyBatchResult,
    RawObject,
    S3BatchStorage,
    S3BatchStorageError,
    StoredCleanedObject,
)


class Body:
    def __init__(self, value, error=None):
        self.value = value
        self.error = error

    def read(self):
        if self.error:
            raise self.error
        return self.value


class FakeS3:
    def __init__(self, pages=None, objects=None):
        self.pages = list(pages or [])
        self.objects = objects or {}
        self.list_calls = []
        self.get_calls = []
        self.put_calls = []
        self.list_error = None
        self.get_error = None
        self.body_error = None
        self.put_error = None

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        if self.list_error:
            raise self.list_error
        return self.pages.pop(0) if self.pages else {"Contents": []}

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.get_error:
            raise self.get_error
        return {"Body": Body(self.objects[kwargs["Key"]], self.body_error)}

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        if self.put_error:
            raise self.put_error


def result(feed_name):
    return DailyBatchResult(feed_name, date(2026, 8, 13), 3, 7, b"parquet", ())


class S3BatchStorageTests(unittest.TestCase):
    def test_loads_paginated_sorted_gzip_objects_and_preserves_bytes(self):
        first = "raw/station_status/year=2026/month=08/day=13/2026-08-13T02-00-00.000000Z.json.gz"
        second = "raw/station_status/year=2026/month=08/day=13/2026-08-13T01-00-00.000000Z.json.gz"
        client = FakeS3(
            pages=[
                {"Contents": [{"Key": first}, {"Key": "ignored.txt"}], "IsTruncated": True, "NextContinuationToken": "next"},
                {"Contents": [{"Key": second}], "IsTruncated": False},
            ],
            objects={first: b"B", second: b"A"},
        )

        loaded = S3BatchStorage("bucket", client).load_raw_objects("station_status", date(2026, 8, 13))

        self.assertEqual([item.object_key for item in loaded], [second, first])
        self.assertEqual([item.compressed_bytes for item in loaded], [b"A", b"B"])
        self.assertEqual(client.list_calls[0], {"Bucket": "bucket", "Prefix": "raw/station_status/year=2026/month=08/day=13/"})
        self.assertEqual(client.list_calls[1]["ContinuationToken"], "next")
        self.assertEqual([call["Key"] for call in client.get_calls], [second, first])

    def test_window_loads_two_utc_partitions_and_obeys_half_open_boundaries(self):
        before = "raw/station_status/year=2026/month=08/day=15/2026-08-15T21-59-59.999999Z.json.gz"
        at_start = "raw/station_status/year=2026/month=08/day=15/2026-08-15T22-00-00.000000Z.json.gz"
        before_end = "raw/station_status/year=2026/month=08/day=16/2026-08-16T21-59-59.999999Z.json.gz"
        at_end = "raw/station_status/year=2026/month=08/day=16/2026-08-16T22-00-00.000000Z.json.gz"
        client = FakeS3(
            pages=[
                {
                    "Contents": [{"Key": before}, {"Key": at_start}],
                    "IsTruncated": True,
                    "NextContinuationToken": "next",
                },
                {"Contents": [], "IsTruncated": False},
                {
                    "Contents": [{"Key": before_end}, {"Key": at_end}],
                    "IsTruncated": False,
                },
            ],
            objects={
                at_start: b"start",
                before_end: b"end-minus-epsilon",
            },
        )

        loaded = S3BatchStorage("bucket", client).load_raw_objects_for_window(
            "station_status",
            datetime(2026, 8, 15, 22, tzinfo=UTC),
            datetime(2026, 8, 16, 22, tzinfo=UTC),
        )

        self.assertEqual([item.object_key for item in loaded], [at_start, before_end])
        self.assertEqual([item.compressed_bytes for item in loaded], [b"start", b"end-minus-epsilon"])
        self.assertEqual(
            [call["Prefix"] for call in client.list_calls],
            [
                "raw/station_status/year=2026/month=08/day=15/",
                "raw/station_status/year=2026/month=08/day=15/",
                "raw/station_status/year=2026/month=08/day=16/",
            ],
        )
        self.assertEqual([call["Key"] for call in client.get_calls], [at_start, before_end])

    def test_loads_station_information_prefix_and_empty_prefix(self):
        client = FakeS3(pages=[{"Contents": [], "IsTruncated": False}])
        self.assertEqual(S3BatchStorage("bucket", client).load_raw_objects("station_information", date(2026, 1, 2)), [])
        self.assertEqual(client.list_calls[0]["Prefix"], "raw/station_information/year=2026/month=01/day=02/")

    def test_invalid_feed_names_raise(self):
        storage = S3BatchStorage("bucket", FakeS3())
        for feed_name in ("", "   ", "station/status"):
            with self.subTest(feed_name=feed_name):
                with self.assertRaises(S3BatchStorageError):
                    storage.load_raw_objects(feed_name, date(2026, 8, 13))

    def test_truncated_listing_without_continuation_token_raises(self):
        client = FakeS3(
            pages=[
                {
                    "Contents": [{"Key": "partial.json.gz"}],
                    "IsTruncated": True,
                }
            ]
        )

        with self.assertRaisesRegex(
            S3BatchStorageError, "missing a non-empty NextContinuationToken"
        ):
            S3BatchStorage("bucket", client).load_raw_objects(
                "station_status", date(2026, 8, 13)
            )

    def test_body_read_error_propagates_unchanged(self):
        error = RuntimeError("body read failed")
        client = FakeS3(
            pages=[{"Contents": [{"Key": "snapshot.json.gz"}], "IsTruncated": False}],
            objects={"snapshot.json.gz": b"compressed"},
        )
        client.body_error = error

        with self.assertRaises(RuntimeError) as raised:
            S3BatchStorage("bucket", client).load_raw_objects(
                "station_status", date(2026, 8, 13)
            )
        self.assertIs(raised.exception, error)

    def test_stores_station_status_with_contract_and_metadata(self):
        client = FakeS3()
        stored = S3BatchStorage("bucket", client).store_daily_batch(result("station_status"))
        call = client.put_calls[0]
        self.assertEqual(call["Key"], "cleaned/fact_station_status/year=2026/month=08/day=13/part-000.parquet")
        self.assertEqual(call["Body"], b"parquet")
        self.assertEqual(call["ContentType"], "application/vnd.apache.parquet")
        self.assertNotIn("ContentEncoding", call)
        self.assertEqual(call["Metadata"], {"feed-name": "station_status", "dataset-name": "fact_station_status", "local-date": "2026-08-13", "timezone": "Europe/Warsaw", "snapshot-count": "3", "row-count": "7"})
        self.assertTrue(all(isinstance(value, str) for value in call["Metadata"].values()))
        self.assertEqual(stored, StoredCleanedObject("bucket", call["Key"], 7, 7, 3))

    def test_stores_station_information_and_is_deterministic(self):
        client = FakeS3()
        storage = S3BatchStorage("bucket", client)
        first = storage.store_daily_batch(result("station_information"))
        second = storage.store_daily_batch(result("station_information"))
        self.assertEqual(first.key, "cleaned/dim_station/year=2026/month=08/day=13/part-000.parquet")
        self.assertEqual(first.key, second.key)

    def test_unsupported_feed_raises(self):
        with self.assertRaises(S3BatchStorageError):
            S3BatchStorage("bucket", FakeS3()).store_daily_batch(result("vehicle_types"))

    def test_aws_errors_propagate(self):
        for operation in ("list", "get", "put"):
            client = FakeS3(pages=[{"Contents": [{"Key": "x.json.gz"}], "IsTruncated": False}], objects={"x.json.gz": b"x"})
            error = RuntimeError(operation)
            setattr(client, f"{operation}_error", error)
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(RuntimeError, operation):
                    if operation == "list":
                        S3BatchStorage("bucket", client).load_raw_objects("feed", date(2026, 1, 1))
                    elif operation == "get":
                        S3BatchStorage("bucket", client).load_raw_objects("feed", date(2026, 1, 1))
                    else:
                        S3BatchStorage("bucket", client).store_daily_batch(result("station_status"))


if __name__ == "__main__":
    unittest.main()
