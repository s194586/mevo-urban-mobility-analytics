"""S3 I/O adapter for daily MEVO batch processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3

from .daily_batch import DailyBatchResult, RawObject
from .raw_reader import RawSnapshotReadError, parse_raw_object_key


class S3BatchStorageError(ValueError):
    """Raised when an S3 batch storage contract is violated."""


@dataclass(frozen=True)
class StoredCleanedObject:
    """Details about a cleaned daily batch written to S3."""

    bucket: str
    key: str
    size: int
    row_count: int
    snapshot_count: int


class S3BatchStorage:
    """Load immutable RAW snapshots and store deterministic cleaned batches."""

    _DATASET_NAMES = {
        "station_status": "fact_station_status",
        "station_information": "dim_station",
    }

    def __init__(self, bucket_name: str, s3_client: Any | None = None) -> None:
        self.bucket_name = bucket_name
        self.s3_client = s3_client if s3_client is not None else boto3.client("s3")

    @staticmethod
    def _validate_feed_name(feed_name: str) -> None:
        if (
            not isinstance(feed_name, str)
            or not feed_name.strip()
            or "/" in feed_name
        ):
            raise S3BatchStorageError(
                "feed_name must be a non-empty string without '/': "
                f"{feed_name!r}"
            )

    @classmethod
    def _raw_prefix(cls, feed_name: str, batch_date: date) -> str:
        cls._validate_feed_name(feed_name)
        return (
            f"raw/{feed_name}/year={batch_date:%Y}/month={batch_date:%m}/"
            f"day={batch_date:%d}/"
        )

    @classmethod
    def _cleaned_key(cls, result: DailyBatchResult) -> str:
        try:
            dataset_name = cls._DATASET_NAMES[result.feed_name]
        except KeyError as exc:
            raise S3BatchStorageError(
                f"unsupported daily batch feed_name: {result.feed_name!r}"
            ) from exc
        return (
            f"cleaned/{dataset_name}/year={result.local_date:%Y}/"
            f"month={result.local_date:%m}/day={result.local_date:%d}/part-000.parquet"
        )

    def load_raw_objects(self, feed_name: str, batch_date: date) -> list[RawObject]:
        """Load all gzip RAW objects for a feed and UTC calendar date."""
        prefix = self._raw_prefix(feed_name, batch_date)
        keys = self._list_raw_keys(prefix)

        raw_objects = []
        for key in sorted(keys):
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            raw_objects.append(RawObject(object_key=key, compressed_bytes=response["Body"].read()))
        return raw_objects

    @staticmethod
    def _normalize_utc_window(
        start_utc: datetime, end_utc: datetime
    ) -> tuple[datetime, datetime]:
        if not isinstance(start_utc, datetime) or not isinstance(end_utc, datetime):
            raise S3BatchStorageError("start_utc and end_utc must be datetime values")
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise S3BatchStorageError(
                "start_utc and end_utc must be timezone-aware datetimes"
            )
        start_utc = start_utc.astimezone(UTC)
        end_utc = end_utc.astimezone(UTC)
        if start_utc >= end_utc:
            raise S3BatchStorageError("start_utc must be before end_utc")
        return start_utc, end_utc

    @classmethod
    def _utc_partition_dates(
        cls, start_utc: datetime, end_utc: datetime
    ) -> list[date]:
        current = start_utc.date()
        last = (end_utc - timedelta(microseconds=1)).date()
        dates = []
        while current <= last:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def load_raw_objects_for_window(
        self,
        feed_name: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawObject]:
        """Load only valid RAW snapshots in the half-open UTC interval."""

        start_utc, end_utc = self._normalize_utc_window(start_utc, end_utc)
        candidates: list[tuple[str, datetime]] = []
        for partition_date in self._utc_partition_dates(start_utc, end_utc):
            prefix = self._raw_prefix(feed_name, partition_date)
            for key in self._list_raw_keys(prefix):
                try:
                    parsed_key = parse_raw_object_key(key)
                except RawSnapshotReadError:
                    continue
                if start_utc <= parsed_key.snapshot_ts < end_utc:
                    candidates.append((key, parsed_key.snapshot_ts))

        candidates.sort(key=lambda item: (item[1], item[0]))
        raw_objects = []
        for key, _snapshot_ts in candidates:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            raw_objects.append(
                RawObject(object_key=key, compressed_bytes=response["Body"].read())
            )
        return raw_objects

    def _list_raw_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            request = {"Bucket": self.bucket_name, "Prefix": prefix}
            if continuation_token is not None:
                request["ContinuationToken"] = continuation_token
            response = self.s3_client.list_objects_v2(**request)
            keys.extend(
                item["Key"]
                for item in response.get("Contents", [])
                if item["Key"].endswith(".json.gz")
            )
            if not response.get("IsTruncated", False):
                break
            continuation_token = response.get("NextContinuationToken")
            if not isinstance(continuation_token, str) or not continuation_token:
                raise S3BatchStorageError(
                    "truncated S3 listing is missing a non-empty "
                    "NextContinuationToken"
                )
        return keys

    def store_daily_batch(self, result: DailyBatchResult) -> StoredCleanedObject:
        """Write one deterministic cleaned Parquet object, replacing any prior copy."""
        key = self._cleaned_key(result)
        metadata = {
            "feed-name": str(result.feed_name),
            "dataset-name": self._DATASET_NAMES[result.feed_name],
            "local-date": str(result.local_date),
            "timezone": result.timezone_name,
            "snapshot-count": str(result.snapshot_count),
            "row-count": str(result.row_count),
        }
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=result.parquet_bytes,
            ContentType="application/vnd.apache.parquet",
            Metadata=metadata,
        )
        return StoredCleanedObject(
            bucket=self.bucket_name,
            key=key,
            size=len(result.parquet_bytes),
            row_count=result.row_count,
            snapshot_count=result.snapshot_count,
        )
