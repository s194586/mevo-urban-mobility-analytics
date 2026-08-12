import unittest
from datetime import datetime, timezone

from mevo_transformer import (
    StationStatusValidationError,
    transform_station_status,
)


SNAPSHOT_TS = datetime(2026, 8, 12, 1, 40, 12, tzinfo=timezone.utc)


def station(station_id="8260", **overrides):
    value = {
        "station_id": station_id,
        "is_installed": True,
        "is_renting": True,
        "is_returning": True,
        "last_reported": 1_786_537_080,
        "num_vehicles_available": 4,
        "num_bikes_available": 4,
        "num_docks_available": 6,
        "vehicle_types_available": [
            {"vehicle_type_id": "bike", "count": 1},
            {"vehicle_type_id": "ebike", "count": 3},
        ],
    }
    value.update(overrides)
    return value


def payload(stations=None, **overrides):
    value = {
        "last_updated": 1_786_537_080,
        "ttl": 15,
        "version": "2.3",
        "data": {"stations": stations if stations is not None else [station()]},
    }
    value.update(overrides)
    return value


class StationStatusTransformerTests(unittest.TestCase):
    def test_valid_payload_has_exact_normalized_schema_and_values(self):
        result = transform_station_status(payload(), SNAPSHOT_TS)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.records[0], {
            "snapshot_ts": SNAPSHOT_TS,
            "feed_last_updated": datetime(2026, 8, 12, 12, 18, 0, tzinfo=timezone.utc),
            "station_id": "8260",
            "last_reported": datetime(2026, 8, 12, 12, 18, 0, tzinfo=timezone.utc),
            "is_installed": True,
            "is_renting": True,
            "is_returning": True,
            "bikes_available": 4,
            "classic_bikes_available": 1,
            "ebikes_available": 3,
            "docks_available": 6,
        })

    def test_multiple_stations_create_multiple_rows(self):
        result = transform_station_status(payload([station(), station("8261")]), SNAPSHOT_TS)
        self.assertEqual([row["station_id"] for row in result.records], ["8260", "8261"])

    def test_missing_bike_normalizes_to_zero(self):
        value = station(
            num_bikes_available=3,
            num_vehicles_available=3,
            vehicle_types_available=[{"vehicle_type_id": "ebike", "count": 3}],
        )
        result = transform_station_status(payload([value]), SNAPSHOT_TS)
        self.assertEqual(result.records[0]["classic_bikes_available"], 0)
        self.assertEqual(result.records[0]["ebikes_available"], 3)

    def test_missing_ebike_normalizes_to_zero(self):
        value = station(
            num_bikes_available=1,
            num_vehicles_available=1,
            vehicle_types_available=[{"vehicle_type_id": "bike", "count": 1}],
        )
        result = transform_station_status(payload([value]), SNAPSHOT_TS)
        self.assertEqual(result.records[0]["classic_bikes_available"], 1)
        self.assertEqual(result.records[0]["ebikes_available"], 0)

    def test_duplicate_station_id_is_hard_error(self):
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([station(), station()]), SNAPSHOT_TS)

    def test_missing_station_id_is_hard_error(self):
        value = station()
        del value["station_id"]
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([value]), SNAPSHOT_TS)

    def test_negative_availability_is_hard_error(self):
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([station(num_bikes_available=-1)]), SNAPSHOT_TS)

    def test_integer_bool_is_hard_error(self):
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([station(is_renting=1)]), SNAPSHOT_TS)

    def test_bike_and_ebike_sum_must_match_bikes(self):
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([station(num_bikes_available=5)]), SNAPSHOT_TS)

    def test_duplicate_vehicle_type_id_is_hard_error(self):
        types = [{"vehicle_type_id": "bike", "count": 2}, {"vehicle_type_id": "bike", "count": 2}]
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([station(vehicle_types_available=types)]), SNAPSHOT_TS)

    def test_unknown_vehicle_type_is_warning(self):
        types = station()["vehicle_types_available"] + [{"vehicle_type_id": "cargo", "count": 1}]
        value = station(num_bikes_available=5, vehicle_types_available=types)
        result = transform_station_status(payload([value]), SNAPSHOT_TS)
        self.assertEqual(len(result.records), 1)
        self.assertTrue(any("cargo" in warning for warning in result.warnings))

    def test_unknown_vehicle_type_with_mismatched_total_is_hard_error(self):
        types = station()["vehicle_types_available"] + [{"vehicle_type_id": "cargo", "count": 1}]
        value = station(num_bikes_available=6, vehicle_types_available=types)
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload([value]), SNAPSHOT_TS)

    def test_vehicle_count_mismatch_is_warning(self):
        result = transform_station_status(payload([station(num_vehicles_available=3)]), SNAPSHOT_TS)
        self.assertTrue(any("num_vehicles_available" in warning for warning in result.warnings))

    def test_malformed_stations_is_hard_error(self):
        with self.assertRaises(StationStatusValidationError):
            transform_station_status(payload(data={"stations": {}}), SNAPSHOT_TS)

    def test_timestamps_are_timezone_aware_utc(self):
        row = transform_station_status(payload(), SNAPSHOT_TS).records[0]
        for key in ("snapshot_ts", "feed_last_updated", "last_reported"):
            self.assertIs(row[key].tzinfo, timezone.utc)

    def test_snapshot_ts_is_not_replaced_by_feed_timestamp(self):
        row = transform_station_status(payload(), SNAPSHOT_TS).records[0]
        self.assertEqual(row["snapshot_ts"], SNAPSHOT_TS)
        self.assertNotEqual(row["snapshot_ts"], row["feed_last_updated"])

    def test_metadata_warnings_are_non_fatal(self):
        result = transform_station_status(payload(version="2.2", ttl=0), SNAPSHOT_TS)
        self.assertEqual(len(result.records), 1)
        self.assertTrue(any("version" in warning for warning in result.warnings))
        self.assertTrue(any("ttl" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
