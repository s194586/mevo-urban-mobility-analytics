"""In-memory Parquet writers for cleaned MEVO records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


FACT_STATION_STATUS_SCHEMA = pa.schema(
    [
        pa.field("snapshot_ts", pa.timestamp("us", tz="UTC")),
        pa.field("feed_last_updated", pa.timestamp("us", tz="UTC")),
        pa.field("station_id", pa.string()),
        pa.field("last_reported", pa.timestamp("us", tz="UTC")),
        pa.field("is_installed", pa.bool_()),
        pa.field("is_renting", pa.bool_()),
        pa.field("is_returning", pa.bool_()),
        pa.field("bikes_available", pa.int64()),
        pa.field("classic_bikes_available", pa.int64()),
        pa.field("ebikes_available", pa.int64()),
        pa.field("docks_available", pa.int64()),
    ]
)

DIM_STATION_SCHEMA = pa.schema(
    [
        pa.field("snapshot_ts", pa.timestamp("us", tz="UTC")),
        pa.field("feed_last_updated", pa.timestamp("us", tz="UTC")),
        pa.field("station_id", pa.string()),
        pa.field("station_name", pa.string()),
        pa.field("address", pa.string()),
        pa.field("cross_street", pa.string()),
        pa.field("latitude", pa.float64()),
        pa.field("longitude", pa.float64()),
        pa.field("capacity", pa.int64()),
        pa.field("is_virtual_station", pa.bool_()),
    ]
)


def _write_parquet(records: Iterable[Mapping[str, Any]], schema: pa.Schema) -> bytes:
    """Serialize cleaned records using the supplied stable schema."""
    table = pa.Table.from_pylist(list(records), schema=schema)
    output = pa.BufferOutputStream()
    pq.write_table(table, output, compression="snappy")
    return output.getvalue().to_pybytes()


def write_station_status_parquet(records: Iterable[Mapping[str, Any]]) -> bytes:
    """Return station status records as an in-memory Snappy Parquet file."""
    return _write_parquet(records, FACT_STATION_STATUS_SCHEMA)


def write_station_information_parquet(records: Iterable[Mapping[str, Any]]) -> bytes:
    """Return station information records as an in-memory Snappy Parquet file."""
    return _write_parquet(records, DIM_STATION_SCHEMA)

