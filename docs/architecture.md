# Architecture Notes

## Collection interval

Dynamic station availability changes during the day, so an initial 10-minute interval should provide useful historical resolution without creating unnecessary request volume or storage. The interval can be reviewed after observing the data and costs.

## Dynamic and near-static feeds

`station_status` and `free_bike_status` are dynamic feeds and are the primary candidates for frequent snapshots. `station_information`, `vehicle_types`, and `system_pricing_plans` change much less often, so they can be collected on a separate, lower-frequency schedule.

## RAW data principle

The first copy of each payload should be retained unchanged, with collection metadata and a time-based object layout. Keeping raw data makes later transformations reproducible and allows the processed layer to be rebuilt when assumptions change.

## Why S3, Lambda, and EventBridge are enough initially

Amazon S3 provides durable, inexpensive object storage; Lambda can run a small collector without a continuously running server; and EventBridge Scheduler can invoke it periodically. Together they cover the narrow Sprint 0 requirement with few moving parts.

## Why Airflow and Spark are deferred

The first version has one small collection task and no large-scale transformation workload. Airflow and Spark would add operational and conceptual complexity before the project has a demonstrated need for orchestration or distributed processing. They may be explored later as optional educational modules.
