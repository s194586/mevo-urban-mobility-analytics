# MEVO Urban Mobility Analytics & Forecasting

## Overview

MEVO Urban Mobility Analytics & Forecasting is an educational, portfolio-oriented data analysis, data engineering, and machine learning project built around the MEVO metropolitan bike-sharing system in Poland.

The long-term objective is to turn public mobility data into useful operational insights, including station profiles, availability forecasts, and rebalancing recommendations.

## Problem

Bike-sharing operators need to understand how station availability changes over time and how demand varies across locations, schedules, and external conditions. This project will build a small, understandable pipeline for exploring those questions with historical data.

## Project Goals

- Collect historical MEVO GBFS snapshots reliably.
- Preserve raw data before transforming it.
- Explore usage and availability patterns with Python.
- Add historical weather data and statistical analysis later.
- Build explainable availability forecasts.
- Translate findings into practical rebalancing recommendations.

## Planned Architecture

```text
MEVO GBFS API
      |
      v
AWS Lambda
      |
      v
Amazon S3 RAW
      |
      v
Processed Parquet
      |
      v
Amazon Athena
      |
      v
Pandas / EDA / Statistics
      |
      v
Machine Learning
      |
      v
Rebalancing recommendations
      |
      v
Dashboard
```

The collector, S3 storage layer, and Lambda handler are implemented locally and
the Lambda resource is deployed in AWS. EventBridge invokes dynamic collection
every 10 minutes, and real RAW payloads are stored in S3.

## Current Status

**SPRINT 0 complete — AWS RAW collection**

Sprint 0 is complete. AWS Lambda collects the dynamic feeds `station_status` and
`free_bike_status` every 10 minutes through EventBridge and stores RAW `.json.gz`
payloads in S3. The same code now supports a `reference` mode for
`station_information` and `vehicle_types`.

The separate daily EventBridge schedule for the reference mode is not deployed
yet. The existing dynamic collection and S3 layout remain unchanged. Reference
payloads will naturally use paths such as:

```text
raw/station_information/year=YYYY/month=MM/day=DD/...
raw/vehicle_types/year=YYYY/month=MM/day=DD/...
```

## Sprint 0 Scope

Sprint 0 established reliable raw collection through AWS Lambda, S3 storage, and
EventBridge scheduling. Dynamic feeds are collected every 10 minutes; the
near-static reference feeds are supported by the code and will receive a
separate daily schedule as the next step.

Sprint 1 will cover validation and transformation of RAW data to Parquet, followed
by preparation of SQL queries. Weather collection, Athena, machine learning,
dashboards, Airflow, Spark, EC2, RDS, Redshift, SageMaker, Kafka, Kinesis, and
MWAA are outside the current collector change.

## Planned Data Sources

- MEVO public GBFS feeds: station status, free-bike status, station information, vehicle types, and pricing plans.
- Official IMGW historical weather data in a later sprint.

Feed URLs are discovered from the MEVO GBFS discovery document.

## Repository Structure

```text
.
├── README.md
├── .gitignore
├── pyproject.toml
├── docs/
│   ├── architecture.md
│   └── gbfs_reconnaissance.md
├── scripts/
│   └── build_lambda.ps1
├── src/
│   └── mevo_collector/
│       ├── __init__.py
│       ├── api.py
│       ├── collector.py
│       ├── lambda_handler.py
│       └── s3_storage.py
└── tests/
    ├── __init__.py
    ├── test_collector.py
    ├── test_lambda_handler.py
    └── test_s3_storage.py
```

## Roadmap

1. **Sprint 0:** AWS data collection setup — complete
2. **Sprint 1:** validation, raw data to processed Parquet, and later SQL querying
3. **Sprint 2:** exploratory data analysis
4. **Sprint 3:** IMGW weather and statistical analysis
5. **Sprint 4:** station profiles and inferred/net flows
6. **Sprint 5:** availability forecasting
7. **Sprint 6:** rebalancing recommendations
8. **Sprint 7:** dashboard and portfolio polish
9. **Sprint 8 (optional):** educational Airflow and PySpark modules

## Tech Stack

The initial implementation uses Python and the standard library, plus boto3 for
the S3 storage layer. Current infrastructure includes AWS Lambda, Amazon S3, and
EventBridge. Later analysis may use Parquet, Athena, Pandas, statistical tools,
and machine learning. Technologies will be introduced only when they serve a
concrete project need.

## Development Setup

Python 3.12 or newer is the target runtime.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

The collector uses the Python standard library plus boto3 for the S3 storage
layer. Tests use mocked S3 clients and do not make AWS requests.

## Security / Secrets

Never commit AWS credentials, GitHub tokens, passwords, API tokens, private keys,
`.env` files, or AWS credential files. AWS authentication should use safe,
non-root practices. No credentials are required for the local test suite.

## Project Status

This is an active learning and portfolio project. Sprint 0 is deployed and the
repository is ready for the next explicitly approved stage: Sprint 1 validation,
Parquet transformation, and later SQL querying.

## Lambda Status

The Lambda handler `mevo_collector.lambda_handler.lambda_handler` is deployed in
AWS, and the local deployment package can be built with
`scripts/build_lambda.ps1`. EventBridge invokes dynamic collection every 10
minutes. The `reference` mode is implemented in code, but its separate daily
schedule is not deployed yet.
