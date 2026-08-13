import copy
import unittest
from datetime import datetime, timezone
from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq

from mevo_transformer import (
    DIM_STATION_SCHEMA,
    FACT_STATION_STATUS_SCHEMA,
    write_station_information_parquet,
    write_station_status_parquet,
)


SNAPSHOT_TS = datetime(2026, 8, 12, 1, 40, 12, tzinfo=timezone.utc)
FEED_TS = datetime(2026, 8, 12, 12, 18, tzinfo=timezone.utc)

STATUS_RECORD = {
    "snapshot_ts": SNAPSHOT_TS,
    "feed_last_updated": FEED_TS,
    "station_id": "8260",
    "last_reported": FEED_TS,
    "is_installed": True,
    "is_renting": False,
    "is_returning": True,
    "bikes_available": 4,
    "classic_bikes_available": 1,
    "ebikes_available": 3,
    "docks_available": 6,
}
INFO_RECORD = {
    "snapshot_ts": SNAPSHOT_TS,
    "feed_last_updated": FEED_TS,
    "station_id": "8260",
    "station_name": "GTC001",
    "address": None,
    "cross_street": None,
    "latitude": 54.051164643591726,
    "longitude": 18.811439983764455,
    "capacity": 10,
    "is_virtual_station": True,
}


def read(data):
    return pq.read_table(BytesIO(data))


class ParquetWriterTests(unittest.TestCase):
    def test_status_round_trip_schema_values_and_magic_bytes(self):
        table = read(write_station_status_parquet([STATUS_RECORD]))
        self.assertEqual(table.schema, FACT_STATION_STATUS_SCHEMA)
        self.assertEqual(table.column_names, list(FACT_STATION_STATUS_SCHEMA.names))
        self.assertEqual(table.to_pylist(), [STATUS_RECORD])
        self.assertEqual(table["snapshot_ts"][0].as_py().utcoffset().total_seconds(), 0)
        self.assertTrue(write_station_status_parquet([STATUS_RECORD]).startswith(b"PAR1"))

    def test_information_round_trip_schema_values_and_nullable_fields(self):
        table = read(write_station_information_parquet([INFO_RECORD]))
        self.assertEqual(table.schema, DIM_STATION_SCHEMA)
        self.assertEqual(table.column_names, list(DIM_STATION_SCHEMA.names))
        row = table.to_pylist()[0]
        self.assertEqual(row["address"], None)
        self.assertEqual(row["cross_street"], None)
        self.assertEqual(row["capacity"], 10)
        self.assertEqual(row["is_virtual_station"], True)
        self.assertEqual(table.schema.field("latitude").type, pa.float64())
        self.assertEqual(table.schema.field("longitude").type, pa.float64())

    def test_multiple_rows_and_empty_inputs_keep_explicit_schema(self):
        status = read(write_station_status_parquet([STATUS_RECORD, {**STATUS_RECORD, "station_id": "8261"}]))
        info = read(write_station_information_parquet([INFO_RECORD, {**INFO_RECORD, "station_id": "8261"}]))
        self.assertEqual(status.num_rows, 2)
        self.assertEqual(info.num_rows, 2)
        empty_status = read(write_station_status_parquet([]))
        empty_info = read(write_station_information_parquet([]))
        self.assertEqual(empty_status.num_rows, 0)
        self.assertEqual(empty_info.num_rows, 0)
        self.assertEqual(empty_status.schema, FACT_STATION_STATUS_SCHEMA)
        self.assertEqual(empty_info.schema, DIM_STATION_SCHEMA)

    def test_input_records_are_not_mutated(self):
        status = [copy.deepcopy(STATUS_RECORD)]
        info = [copy.deepcopy(INFO_RECORD)]
        original_status, original_info = copy.deepcopy(status), copy.deepcopy(info)
        write_station_status_parquet(status)
        write_station_information_parquet(info)
        self.assertEqual(status, original_status)
        self.assertEqual(info, original_info)


if __name__ == "__main__":
    unittest.main()
