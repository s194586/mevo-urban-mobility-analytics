import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from mevo_collector.collector import CollectionResult, FeedSnapshot
from mevo_collector.lambda_handler import LambdaInvocationError, lambda_handler
from mevo_collector.s3_storage import StoredObject


def snapshot(feed_name: str) -> FeedSnapshot:
    key = {
        "station_status": "stations",
        "free_bike_status": "bikes",
        "station_information": "stations",
        "vehicle_types": "vehicle_types",
    }[feed_name]
    return FeedSnapshot(
        feed_name=feed_name,
        source_url=f"https://example.test/{feed_name}.json",
        collected_at=datetime(2026, 8, 12, 1, 40, 12, tzinfo=timezone.utc),
        source_last_updated=None,
        raw_bytes=b"{}",
        parsed={"data": {key: []}},
    )


class LambdaHandlerTests(unittest.TestCase):
    def collection(self, feeds, errors=None):
        return CollectionResult(
            collected_at=datetime(2026, 8, 12, 1, 40, 12, tzinfo=timezone.utc),
            feeds={name: snapshot(name) for name in feeds},
            errors=errors or {},
        )

    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_missing_bucket_fails_before_collection(self, collect):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MEVO_RAW_BUCKET"):
                lambda_handler({}, None)
        collect.assert_not_called()

    @patch("mevo_collector.lambda_handler.S3Storage")
    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_full_success_returns_json_serializable_result(self, collect, storage_class):
        collect.return_value = self.collection(["station_status", "free_bike_status"])
        storage = storage_class.return_value
        storage.store.side_effect = lambda item: StoredObject("bucket", f"raw/{item.feed_name}", 10, 20)

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            result = lambda_handler({}, None)

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["feeds"]), 2)
        self.assertEqual(result["errors"], {})
        json.dumps(result)
        storage_class.assert_called_once_with("bucket")

    @patch("mevo_collector.lambda_handler.S3Storage")
    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_empty_event_uses_dynamic_mode(self, collect, storage_class):
        collect.return_value = self.collection(["station_status", "free_bike_status"])
        storage_class.return_value.store.side_effect = lambda item: StoredObject("bucket", "key", 1, 1)

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            lambda_handler({}, None)

        collect.assert_called_once_with(feed_names=("station_status", "free_bike_status"))

    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_reference_mode_collects_reference_feeds(self, collect):
        collect.return_value = self.collection(["station_information", "vehicle_types"])

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with patch("mevo_collector.lambda_handler.S3Storage") as storage_class:
                storage_class.return_value.store.side_effect = lambda item: StoredObject("bucket", "key", 1, 1)
                lambda_handler({"mode": "reference"}, None)

        collect.assert_called_once_with(feed_names=("station_information", "vehicle_types"))

    def test_unknown_mode_is_a_clear_error(self):
        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaisesRegex(ValueError, "Unsupported collection mode"):
                lambda_handler({"mode": "weekly"}, None)

    @patch("mevo_collector.lambda_handler.S3Storage")
    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_partial_failure_stores_success_and_raises(self, collect, storage_class):
        collect.return_value = self.collection(["station_status"], {"free_bike_status": "API failed"})
        storage_class.return_value.store.return_value = StoredObject("bucket", "raw/stations", 2, 3)

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaises(LambdaInvocationError) as raised:
                lambda_handler({}, None)

        storage_class.return_value.store.assert_called_once()
        self.assertEqual(raised.exception.result["status"], "partial_failure")
        self.assertEqual(raised.exception.result["errors"], {"free_bike_status": "API failed"})

    @patch("mevo_collector.lambda_handler.S3Storage")
    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_total_failure_does_not_create_storage_or_upload(self, collect, storage_class):
        collect.return_value = self.collection([], {"station_status": "A", "free_bike_status": "B"})

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaises(LambdaInvocationError) as raised:
                lambda_handler({}, None)

        storage_class.assert_not_called()
        self.assertEqual(raised.exception.result["status"], "total_failure")

    @patch("mevo_collector.lambda_handler.S3Storage")
    @patch("mevo_collector.lambda_handler.collect_snapshot")
    def test_s3_upload_error_propagates(self, collect, storage_class):
        collect.return_value = self.collection(["station_status"])
        storage_class.return_value.store.side_effect = RuntimeError("S3 failure")

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "S3 failure"):
                lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
