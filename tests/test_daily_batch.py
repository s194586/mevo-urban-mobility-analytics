import copy
import gzip
import json
import unittest
from datetime import UTC, date, datetime
from io import BytesIO

import pyarrow.parquet as pq

from mevo_transformer import (
    DIM_STATION_SCHEMA,
    FACT_STATION_STATUS_SCHEMA,
    DailyBatchError,
    RawObject,
    build_station_information_daily_batch,
    build_station_status_daily_batch,
)


def compressed(payload):
    return gzip.compress(json.dumps(payload).encode("utf-8"))


def key(feed, timestamp, day="12"):
    return f"raw/{feed}/year=2026/month=08/day={day}/{timestamp}.json.gz"


def status_station(station_id):
    return {
        "station_id": station_id,
        "is_installed": True,
        "is_renting": True,
        "is_returning": False,
        "last_reported": 1_786_537_080,
        "num_vehicles_available": 4,
        "num_bikes_available": 4,
        "num_docks_available": 6,
        "vehicle_types_available": [
            {"vehicle_type_id": "bike", "count": 1},
            {"vehicle_type_id": "ebike", "count": 3},
        ],
    }


def info_station(station_id):
    return {
        "station_id": station_id,
        "name": f"Station {station_id}",
        "lat": 54.05,
        "lon": 18.81,
        "capacity": 10,
        "is_virtual_station": False,
    }


def payload(stations, **metadata):
    return {
        "last_updated": 1_786_537_080,
        "ttl": 15,
        "version": "2.3",
        "data": {"stations": stations},
        **metadata,
    }


class DailyBatchTests(unittest.TestCase):
    def test_station_status_orders_snapshots_and_stations_and_uses_fact_schema(self):
        early = RawObject(
            key("station_status", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([status_station("B"), status_station("A")])),
        )
        late = RawObject(
            key("station_status", "2026-08-12T02-00-00.000000Z"),
            compressed(payload([status_station("A")])),
        )

        result = build_station_status_daily_batch([late, early], date(2026, 8, 12))
        table = pq.read_table(BytesIO(result.parquet_bytes))

        self.assertEqual(result.feed_name, "station_status")
        self.assertEqual(result.local_date, date(2026, 8, 12))
        self.assertEqual(result.snapshot_count, 2)
        self.assertEqual(result.row_count, 3)
        self.assertEqual(table.schema, FACT_STATION_STATUS_SCHEMA)
        self.assertEqual(
            [(row["snapshot_ts"], row["station_id"]) for row in table.to_pylist()],
            [
                (datetime(2026, 8, 12, 1, tzinfo=UTC), "A"),
                (datetime(2026, 8, 12, 1, tzinfo=UTC), "B"),
                (datetime(2026, 8, 12, 2, tzinfo=UTC), "A"),
            ],
        )

    def test_station_information_multiple_snapshots_uses_dim_schema(self):
        objects = [
            RawObject(
                key("station_information", "2026-08-12T03-00-00.000000Z"),
                compressed(payload([info_station("A"), info_station("B")])),
            ),
            RawObject(
                key("station_information", "2026-08-12T01-00-00.000000Z"),
                compressed(payload([info_station("A")])),
            ),
        ]
        result = build_station_information_daily_batch(objects, date(2026, 8, 12))
        table = pq.read_table(BytesIO(result.parquet_bytes))

        self.assertEqual(result.snapshot_count, 2)
        self.assertEqual(result.row_count, 3)
        self.assertEqual(table.schema, DIM_STATION_SCHEMA)
        self.assertEqual([row["station_id"] for row in table.to_pylist()], ["A", "A", "B"])

    def test_single_station_information_snapshot_has_expected_result_and_schema(self):
        raw_object = RawObject(
            key("station_information", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([info_station("A")])),
        )

        result = build_station_information_daily_batch([raw_object], date(2026, 8, 12))
        table = pq.read_table(BytesIO(result.parquet_bytes))

        self.assertEqual(result.snapshot_count, 1)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(table.schema, DIM_STATION_SCHEMA)

    def test_empty_mismatch_cross_day_and_duplicate_are_batch_errors(self):
        with self.assertRaises(DailyBatchError):
            build_station_status_daily_batch([], date(2026, 8, 12))

        info_object = RawObject(
            key("station_information", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([info_station("A")])),
        )
        with self.assertRaises(DailyBatchError):
            build_station_status_daily_batch([info_object], date(2026, 8, 12))

        next_day = RawObject(
            key("station_status", "2026-08-13T01-00-00.000000Z", day="13"),
            compressed(payload([status_station("A")])),
        )
        first_day = RawObject(
            key("station_status", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([status_station("A")])),
        )
        with self.assertRaises(DailyBatchError):
            build_station_status_daily_batch([first_day, next_day], date(2026, 8, 12))
        with self.assertRaises(DailyBatchError):
            build_station_status_daily_batch(
                [first_day, copy.copy(first_day)], date(2026, 8, 12)
            )

    def test_one_local_day_can_span_two_utc_partition_dates(self):
        previous_utc_day = RawObject(
            key(
                "station_status",
                "2026-08-11T23-00-00.000000Z",
                day="11",
            ),
            compressed(payload([status_station("A")])),
        )
        current_utc_day = RawObject(
            key("station_status", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([status_station("A")])),
        )

        result = build_station_status_daily_batch(
            [current_utc_day, previous_utc_day], date(2026, 8, 12)
        )

        self.assertEqual(result.local_date, date(2026, 8, 12))
        self.assertEqual(result.snapshot_count, 2)

    def test_snapshot_outside_local_date_is_a_batch_error(self):
        raw = RawObject(
            key("station_status", "2026-08-12T22-00-00.000000Z"),
            compressed(payload([status_station("A")])),
        )
        with self.assertRaises(DailyBatchError):
            build_station_status_daily_batch([raw], date(2026, 8, 12))

    def test_warnings_are_prefixed_and_input_is_not_mutated(self):
        raw = RawObject(
            key("station_status", "2026-08-12T01-00-00.000000Z"),
            compressed(payload([status_station("A")], ttl=0)),
        )
        before = copy.deepcopy(raw)

        result = build_station_status_daily_batch([raw], date(2026, 8, 12))

        self.assertEqual(raw, before)
        self.assertIsInstance(result.warnings, tuple)
        self.assertTrue(any(warning.startswith(raw.object_key + ": ") for warning in result.warnings))
        self.assertTrue(any("ttl is unusual" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
