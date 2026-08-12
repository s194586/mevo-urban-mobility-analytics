import math
import unittest
from datetime import datetime, timedelta, timezone

from mevo_transformer import (
    StationInformationValidationError,
    transform_station_information,
)


SNAPSHOT_TS = datetime(2026, 8, 12, 1, 40, 12, tzinfo=timezone.utc)


def station(station_id="8260", **overrides):
    value = {
        "station_id": station_id,
        "name": "GTC001",
        "address": "Makowa 7, 83-110 Tczew",
        "cross_street": "Makowa 7, 83-110 Tczew",
        "lat": 54.051164643591726,
        "lon": 18.811439983764455,
        "is_virtual_station": True,
        "capacity": 10,
        "station_area": {"type": "MultiPolygon", "coordinates": []},
        "rental_uris": {"android": "...", "ios": "..."},
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


class StationInformationTransformerTests(unittest.TestCase):
    def test_valid_payload_has_exact_cleaned_schema_and_values(self):
        result = transform_station_information(payload(), SNAPSHOT_TS)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.records[0], {
            "snapshot_ts": SNAPSHOT_TS,
            "feed_last_updated": datetime(2026, 8, 12, 12, 18, tzinfo=timezone.utc),
            "station_id": "8260",
            "station_name": "GTC001",
            "address": "Makowa 7, 83-110 Tczew",
            "cross_street": "Makowa 7, 83-110 Tczew",
            "latitude": 54.051164643591726,
            "longitude": 18.811439983764455,
            "capacity": 10,
            "is_virtual_station": True,
        })

    def test_multiple_stations_create_multiple_rows(self):
        result = transform_station_information(payload([station(), station("8261")]), SNAPSHOT_TS)
        self.assertEqual([row["station_id"] for row in result.records], ["8260", "8261"])

    def test_snapshot_is_canonical_and_not_feed_timestamp(self):
        local_snapshot = datetime(2026, 8, 12, 3, 40, 12, tzinfo=timezone(timedelta(hours=2)))
        row = transform_station_information(payload(), local_snapshot).records[0]
        self.assertEqual(row["snapshot_ts"], SNAPSHOT_TS)
        self.assertNotEqual(row["snapshot_ts"], row["feed_last_updated"])

    def test_timestamps_are_timezone_aware_utc(self):
        row = transform_station_information(payload(), SNAPSHOT_TS).records[0]
        for key in ("snapshot_ts", "feed_last_updated"):
            self.assertIs(row[key].tzinfo, timezone.utc)

    def test_duplicate_station_id_is_hard_error(self):
        with self.assertRaises(StationInformationValidationError):
            transform_station_information(payload([station(), station()]), SNAPSHOT_TS)

    def test_required_identifiers_and_name_are_non_empty_strings(self):
        for changes in ({"station_id": None}, {"station_id": "  "}, {"name": None}, {"name": ""}):
            with self.subTest(changes=changes), self.assertRaises(StationInformationValidationError):
                transform_station_information(payload([station(**changes)]), SNAPSHOT_TS)

    def test_coordinate_validation_rejects_range_nan_infinity_and_bool(self):
        for field, value in (("lat", -91), ("lat", 91), ("lon", -181), ("lon", 181),
                             ("lat", math.nan), ("lon", math.inf), ("lat", True), ("lon", False)):
            with self.subTest(field=field, value=value), self.assertRaises(StationInformationValidationError):
                transform_station_information(payload([station(**{field: value})]), SNAPSHOT_TS)

    def test_capacity_and_virtual_station_validation(self):
        for changes in ({"capacity": -1}, {"capacity": True}, {"is_virtual_station": 1}):
            with self.subTest(changes=changes), self.assertRaises(StationInformationValidationError):
                transform_station_information(payload([station(**changes)]), SNAPSHOT_TS)

    def test_optional_location_fields_normalize_and_validate(self):
        for field in ("address", "cross_street"):
            value = station()
            del value[field]
            self.assertIsNone(transform_station_information(payload([value]), SNAPSHOT_TS).records[0][field])
            self.assertIsNone(transform_station_information(payload([station(**{field: None})]), SNAPSHOT_TS).records[0][field])
            with self.assertRaises(StationInformationValidationError):
                transform_station_information(payload([station(**{field: 7})]), SNAPSHOT_TS)

    def test_malformed_data_stations_is_hard_error(self):
        with self.assertRaises(StationInformationValidationError):
            transform_station_information({"last_updated": 0, "data": {"stations": {}}}, SNAPSHOT_TS)

    def test_metadata_warnings_are_non_fatal(self):
        for changes in ({"version": "2.2", "ttl": 0}, {"ttl": None}, {"ttl": "15"},):
            result = transform_station_information(payload(**changes), SNAPSHOT_TS)
            self.assertEqual(len(result.records), 1)
            if "version" in changes:
                self.assertTrue(any("version" in warning for warning in result.warnings))
            self.assertTrue(any("ttl" in warning for warning in result.warnings))

    def test_missing_ttl_is_warning_and_excluded_fields_are_not_cleaned(self):
        value = payload()
        del value["ttl"]
        row = transform_station_information(value, SNAPSHOT_TS).records[0]
        self.assertTrue(row)
        self.assertNotIn("station_area", row)
        self.assertNotIn("rental_uris", row)


if __name__ == "__main__":
    unittest.main()
