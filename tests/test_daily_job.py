import gzip
import json
import unittest
from datetime import date

from mevo_transformer import DailyBatchError, DailyJobError, StoredCleanedObject, run_daily_batch


class Body:
    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value


class FakeS3:
    def __init__(self, objects=None, list_error=None, get_error=None, put_error=None):
        self.objects = objects or {}
        self.list_error = list_error
        self.get_error = get_error
        self.put_error = put_error
        self.put_calls = []

    def list_objects_v2(self, **kwargs):
        if self.list_error:
            raise self.list_error
        keys = [{"Key": key} for key in self.objects if key.startswith(kwargs["Prefix"])]
        return {"Contents": keys, "IsTruncated": False}

    def get_object(self, **kwargs):
        if self.get_error:
            raise self.get_error
        return {"Body": Body(self.objects[kwargs["Key"]])}

    def put_object(self, **kwargs):
        if self.put_error:
            raise self.put_error
        self.put_calls.append(kwargs)


def compressed(payload):
    return gzip.compress(json.dumps(payload).encode())


def payload(stations, ttl=15):
    return {"last_updated": 1786537080, "ttl": ttl, "version": "2.3", "data": {"stations": stations}}


def status_station(station_id="A"):
    return {"station_id": station_id, "is_installed": True, "is_renting": True,
            "is_returning": False, "last_reported": 1786537080,
            "num_vehicles_available": 1, "num_bikes_available": 1,
            "num_docks_available": 2,
            "vehicle_types_available": [{"vehicle_type_id": "bike", "count": 1}]}


def info_station(station_id="A"):
    return {"station_id": station_id, "name": "Station " + station_id,
            "lat": 54.05, "lon": 18.81, "capacity": 10, "is_virtual_station": False}


def raw_key(feed, hour="01"):
    return f"raw/{feed}/year=2026/month=08/day=13/2026-08-13T{hour}-00-00.000000Z.json.gz"


class DailyJobTests(unittest.TestCase):
    def test_station_status_runs_end_to_end_and_returns_summary(self):
        client = FakeS3({raw_key("station_status"): compressed(payload([status_station()], ttl=0))})
        result = run_daily_batch("bucket", "station_status", date(2026, 8, 13), client)

        self.assertEqual(result.feed_name, "station_status")
        self.assertEqual(result.local_date, date(2026, 8, 13))
        self.assertEqual(result.snapshot_count, 1)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.warning_count, 1)
        self.assertEqual(result.cleaned_object.bucket, "bucket")
        self.assertEqual(result.cleaned_object.key, "cleaned/fact_station_status/year=2026/month=08/day=13/part-000.parquet")
        self.assertEqual(result.cleaned_object.size, len(client.put_calls[0]["Body"]))
        self.assertEqual(result.cleaned_object.row_count, 1)
        self.assertEqual(result.cleaned_object.snapshot_count, 1)
        self.assertTrue(client.put_calls[0]["Body"].startswith(b"PAR1"))

    def test_station_information_runs_end_to_end_with_dim_key(self):
        client = FakeS3({raw_key("station_information"): compressed(payload([info_station()]))})
        result = run_daily_batch("bucket", "station_information", date(2026, 8, 13), client)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.cleaned_object.key, "cleaned/dim_station/year=2026/month=08/day=13/part-000.parquet")
        self.assertTrue(client.put_calls[0]["Body"].startswith(b"PAR1"))

    def test_unsupported_empty_and_s3_errors(self):
        with self.assertRaises(DailyJobError):
            run_daily_batch("bucket", "vehicle_types", date(2026, 8, 13), FakeS3())
        with self.assertRaises(DailyBatchError):
            run_daily_batch("bucket", "station_status", date(2026, 8, 13), FakeS3())
        error = RuntimeError("S3 failed")
        with self.assertRaisesRegex(RuntimeError, "S3 failed"):
            run_daily_batch("bucket", "station_status", date(2026, 8, 13), FakeS3(list_error=error))


if __name__ == "__main__":
    unittest.main()
