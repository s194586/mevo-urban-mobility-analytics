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

Everything after the initial repository bootstrap is planned work. No AWS infrastructure or data collection has been implemented yet.

## Current Status

**SPRINT 0 — bootstrap / data collection setup**

The in-memory MEVO collector core is implemented. It discovers dynamic feed URLs and preserves successful raw payloads; AWS storage and scheduling have not been implemented.

## Sprint 0 Scope

The next stages of Sprint 0 will, incrementally and with explicit review, verify the public feeds, implement a simple Python collector, and later deploy it to AWS Lambda with S3 storage and EventBridge scheduling. Dynamic feeds are expected to be collected approximately every 10 minutes; near-static feeds will be collected less frequently.

Out of scope for this sprint are weather collection, Athena, machine learning, dashboards, Airflow, Spark, EC2, RDS, Redshift, SageMaker, Kafka, Kinesis, and MWAA.

## Planned Data Sources

- MEVO public GBFS feeds: station status, free-bike status, station information, vehicle types, and pricing plans.
- Official IMGW historical weather data in a later sprint.

Exact MEVO endpoint URLs will be verified before implementation.

## Planned Repository Structure

```text
.
├── README.md
├── .gitignore
├── pyproject.toml
├── docs/
│   └── architecture.md
├── src/
│   └── mevo_collector/
│       └── __init__.py
└── tests/
    └── __init__.py
```

## Roadmap

1. **Sprint 0:** AWS data collection setup
2. **Sprint 1:** raw data to processed Parquet, Athena, and Pandas
3. **Sprint 2:** exploratory data analysis
4. **Sprint 3:** IMGW weather and statistical analysis
5. **Sprint 4:** station profiles and inferred/net flows
6. **Sprint 5:** availability forecasting
7. **Sprint 6:** rebalancing recommendations
8. **Sprint 7:** dashboard and portfolio polish
9. **Sprint 8 (optional):** educational Airflow and PySpark modules

## Tech Stack

The initial implementation uses Python and the standard library. Planned infrastructure includes AWS Lambda, Amazon S3, and EventBridge; later analysis may use Parquet, Athena, Pandas, and machine learning tools. Technologies will be introduced only when they serve a concrete project need.

## Development Setup

Python 3.12 or newer is the target runtime.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

The collector uses only the Python standard library. There are currently no runtime dependencies or test dependencies to install.

## Security / Secrets

Never commit AWS credentials, GitHub tokens, passwords, API tokens, private keys, `.env` files, or AWS credential files. AWS authentication will be configured later using safe, non-root practices. No credentials are required for the current bootstrap.

## Project Status

This is an active learning project. The repository is at the bootstrap stage and is ready for the next explicitly approved stage.
