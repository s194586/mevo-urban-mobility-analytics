import json
import os
import unittest
from datetime import UTC, date, datetime
from unittest.mock import call, patch

from mevo_transformer.daily_job import DailyJobResult
from mevo_transformer.lambda_handler import lambda_handler, previous_local_date
from mevo_transformer.s3_batch_storage import StoredCleanedObject


def job_result(feed_name: str, local_date: date) -> DailyJobResult:
    dataset = "fact_station_status" if feed_name == "station_status" else "dim_station"
    return DailyJobResult(
        feed_name=feed_name,
        local_date=local_date,
        snapshot_count=3,
        row_count=12,
        warning_count=1,
        cleaned_object=StoredCleanedObject(
            bucket="bucket",
            key=(
                f"cleaned/{dataset}/year={local_date:%Y}/"
                f"month={local_date:%m}/day={local_date:%d}/part-000.parquet"
            ),
            size=100,
            row_count=12,
            snapshot_count=3,
        ),
    )


class TransformerLambdaHandlerTests(unittest.TestCase):
    def test_previous_local_date_summer(self):
        now_utc = datetime(2026, 7, 20, 1, 30, tzinfo=UTC)

        self.assertEqual(previous_local_date(now_utc), date(2026, 7, 19))

    def test_previous_local_date_winter(self):
        now_utc = datetime(2026, 1, 20, 1, 30, tzinfo=UTC)

        self.assertEqual(previous_local_date(now_utc), date(2026, 1, 19))

    def test_previous_local_date_uses_warsaw_around_utc_midnight(self):
        now_utc = datetime(2026, 8, 17, 22, 30, tzinfo=UTC)

        self.assertEqual(previous_local_date(now_utc), date(2026, 8, 17))

    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_manual_local_date_is_used(self, run_batch):
        local_date = date(2026, 8, 16)
        run_batch.side_effect = [
            job_result("station_status", local_date),
            job_result("station_information", local_date),
        ]

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            result = lambda_handler({"local_date": "2026-08-16"}, None)

        self.assertEqual(result["local_date"], "2026-08-16")
        self.assertEqual(
            run_batch.call_args_list,
            [
                call("bucket", "station_status", local_date),
                call("bucket", "station_information", local_date),
            ],
        )

    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_invalid_manual_local_date_fails_before_processing(self, run_batch):
        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaisesRegex(ValueError, "local_date"):
                lambda_handler({"local_date": "2026-02-30"}, None)

        run_batch.assert_not_called()

    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_missing_bucket_fails_before_processing(self, run_batch):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MEVO_RAW_BUCKET"):
                lambda_handler({"local_date": "2026-08-16"}, None)

        run_batch.assert_not_called()

    @patch("mevo_transformer.lambda_handler.previous_local_date")
    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_handler_runs_both_feeds_with_same_automatic_local_date(
        self, run_batch, previous_date
    ):
        local_date = date(2026, 8, 17)
        previous_date.return_value = local_date
        run_batch.side_effect = [
            job_result("station_status", local_date),
            job_result("station_information", local_date),
        ]

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            result = lambda_handler({}, None)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["local_date"], "2026-08-17")
        self.assertEqual(result["timezone"], "Europe/Warsaw")
        self.assertEqual([feed["feed_name"] for feed in result["feeds"]], [
            "station_status",
            "station_information",
        ])
        json.dumps(result)
        self.assertEqual(
            run_batch.call_args_list,
            [
                call("bucket", "station_status", local_date),
                call("bucket", "station_information", local_date),
            ],
        )

    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_first_batch_error_propagates(self, run_batch):
        error = RuntimeError("station_status failed")
        run_batch.side_effect = error

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                lambda_handler({"local_date": "2026-08-16"}, None)

        self.assertIs(raised.exception, error)
        self.assertEqual(run_batch.call_count, 1)

    @patch("mevo_transformer.lambda_handler.run_daily_batch")
    def test_second_batch_error_propagates(self, run_batch):
        local_date = date(2026, 8, 16)
        error = RuntimeError("station_information failed")
        run_batch.side_effect = [job_result("station_status", local_date), error]

        with patch.dict(os.environ, {"MEVO_RAW_BUCKET": "bucket"}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                lambda_handler({"local_date": "2026-08-16"}, None)

        self.assertIs(raised.exception, error)
        self.assertEqual(run_batch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
