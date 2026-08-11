"""In-memory gzip compression and S3 storage for collected MEVO snapshots."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import timezone
from typing import Any

import boto3

from .collector import FeedSnapshot


@dataclass(frozen=True)
class StoredObject:
    """Details about an object written to S3."""

    bucket: str
    key: str
    raw_size: int
    compressed_size: int


class S3Storage:
    """Store raw feed payloads as gzip-compressed objects in S3."""

    def __init__(self, bucket_name: str, s3_client: Any | None = None) -> None:
        self.bucket_name = bucket_name
        self.s3_client = s3_client if s3_client is not None else boto3.client("s3")

    @staticmethod
    def _object_key(snapshot: FeedSnapshot) -> str:
        collected_at = snapshot.collected_at
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        collected_at = collected_at.astimezone(timezone.utc)
        timestamp = collected_at.strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        return (
            f"raw/{snapshot.feed_name}/year={collected_at:%Y}/"
            f"month={collected_at:%m}/day={collected_at:%d}/{timestamp}.json.gz"
        )

    def store(self, snapshot: FeedSnapshot) -> StoredObject:
        """Compress and write one snapshot, propagating any S3 exception."""
        compressed = gzip.compress(snapshot.raw_bytes)
        key = self._object_key(snapshot)
        metadata = {
            "feed-name": snapshot.feed_name,
            "collected-at": snapshot.collected_at.isoformat(),
        }
        if snapshot.source_last_updated is not None:
            metadata["source-last-updated"] = str(snapshot.source_last_updated)

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=compressed,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata=metadata,
        )
        return StoredObject(self.bucket_name, key, len(snapshot.raw_bytes), len(compressed))
