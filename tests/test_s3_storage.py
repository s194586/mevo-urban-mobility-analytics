import gzip
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from mevo_collector import FeedSnapshot, S3Storage


class S3StorageTests(unittest.TestCase):
    def make_snapshot(self, source_last_updated=1723420800):
        return FeedSnapshot(
            feed_name="station_status",
            source_url="https://example.test/stations.json",
            collected_at=datetime(2026, 8, 12, 1, 40, 12, 123456, tzinfo=timezone.utc),
            source_last_updated=source_last_updated,
            raw_bytes=b'{"data":{"stations":[{"station_id":"1"}]}}',
            parsed={"data": {"stations": []}},
        )

    def test_store_writes_gzip_object_and_returns_details(self):
        client = Mock()
        snapshot = self.make_snapshot()
        result = S3Storage("mevo-raw-test", s3_client=client).store(snapshot)
        call = client.put_object.call_args.kwargs
        self.assertEqual(result.bucket, "mevo-raw-test")
        self.assertEqual(result.key, "raw/station_status/year=2026/month=08/day=12/2026-08-12T01-40-12.123456Z.json.gz")
        self.assertEqual(call["Bucket"], result.bucket)
        self.assertEqual(call["Key"], result.key)
        self.assertEqual(gzip.decompress(call["Body"]), snapshot.raw_bytes)
        self.assertEqual(result.raw_size, len(snapshot.raw_bytes))
        self.assertEqual(result.compressed_size, len(call["Body"]))
        self.assertEqual(call["ContentType"], "application/json")
        self.assertEqual(call["ContentEncoding"], "gzip")

    def test_metadata_includes_optional_source_last_updated(self):
        client = Mock()
        S3Storage("bucket", s3_client=client).store(self.make_snapshot())
        self.assertEqual(client.put_object.call_args.kwargs["Metadata"], {
            "feed-name": "station_status",
            "collected-at": "2026-08-12T01:40:12.123456+00:00",
            "source-last-updated": "1723420800",
        })

    def test_non_utc_collected_at_is_normalized_in_key_and_metadata(self):
        client = Mock()
        local_time = datetime(2026, 8, 12, 3, 40, 12, 123456, tzinfo=timezone(timedelta(hours=2)))
        snapshot = self.make_snapshot()
        snapshot = FeedSnapshot(
            feed_name=snapshot.feed_name,
            source_url=snapshot.source_url,
            collected_at=local_time,
            source_last_updated=snapshot.source_last_updated,
            raw_bytes=snapshot.raw_bytes,
            parsed=snapshot.parsed,
        )

        result = S3Storage("bucket", s3_client=client).store(snapshot)
        metadata_time = datetime.fromisoformat(client.put_object.call_args.kwargs["Metadata"]["collected-at"])

        self.assertIn("year=2026/month=08/day=12/2026-08-12T01-40-12.123456Z.json.gz", result.key)
        self.assertEqual(metadata_time, datetime(2026, 8, 12, 1, 40, 12, 123456, tzinfo=timezone.utc))
        self.assertEqual(metadata_time, local_time.astimezone(timezone.utc))

    def test_source_last_updated_metadata_is_omitted_when_missing(self):
        client = Mock()
        S3Storage("bucket", s3_client=client).store(self.make_snapshot(None))
        self.assertNotIn("source-last-updated", client.put_object.call_args.kwargs["Metadata"])

    def test_s3_error_is_propagated(self):
        client = Mock()
        client.put_object.side_effect = RuntimeError("S3 failure")
        with self.assertRaisesRegex(RuntimeError, "S3 failure"):
            S3Storage("bucket", s3_client=client).store(self.make_snapshot())


if __name__ == "__main__":
    unittest.main()
