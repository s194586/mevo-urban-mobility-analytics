"""AWS Lambda entry point for collecting and storing MEVO feed snapshots."""

from __future__ import annotations

import logging
import os
from typing import Any

from .collector import CollectionResult, collect_snapshot
from .s3_storage import S3Storage

logger = logging.getLogger(__name__)

MODE_FEEDS = {
    "dynamic": ("station_status", "free_bike_status"),
    "reference": ("station_information", "vehicle_types"),
}


class LambdaInvocationError(RuntimeError):
    """Raised when collection completed with feed errors."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


def _result_base(collection: CollectionResult, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "collected_at": collection.collected_at.isoformat(),
        "feeds": [],
        "errors": dict(collection.errors),
    }


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Collect MEVO feeds and store successful snapshots in S3."""
    mode = event.get("mode", "dynamic") if isinstance(event, dict) else "dynamic"
    if mode not in MODE_FEEDS:
        raise ValueError(f"Unsupported collection mode: {mode!r}")
    logger.info("Starting MEVO collection invocation mode=%s", mode)
    try:
        bucket = os.environ["MEVO_RAW_BUCKET"]
    except KeyError as exc:
        raise RuntimeError("Missing required environment variable: MEVO_RAW_BUCKET") from exc

    collection = collect_snapshot(feed_names=MODE_FEEDS[mode])
    if collection.total_failure:
        result = _result_base(collection, "total_failure")
        logger.error("Total collection failure: %s", collection.errors)
        raise LambdaInvocationError("All MEVO feeds failed", result)

    storage = S3Storage(bucket)
    result = _result_base(collection, "success" if not collection.errors else "partial_failure")
    for feed_name, snapshot in collection.feeds.items():
        stored = storage.store(snapshot)
        feed_result = {
            "feed": feed_name,
            "bucket": stored.bucket,
            "key": stored.key,
            "raw_size": stored.raw_size,
            "compressed_size": stored.compressed_size,
        }
        result["feeds"].append(feed_result)
        logger.info(
            "SUCCESS feed=%s key=%s raw_bytes=%d compressed_bytes=%d",
            feed_name,
            stored.key,
            stored.raw_size,
            stored.compressed_size,
        )

    if collection.errors:
        logger.error("Partial collection failure: %s", collection.errors)
        raise LambdaInvocationError("One or more MEVO feeds failed", result)

    logger.info("MEVO collection completed collected_at=%s", result["collected_at"])
    return result
