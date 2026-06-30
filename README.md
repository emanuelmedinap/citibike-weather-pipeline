# citibike-weather-pipeline

NYC Citibike ridership vs weather — an end-to-end data pipeline.

> NYU Stern MSBA · *Dealing With Data* (Prof. Panos Ipeirotis), 2026
> Individual coursework, built as a portfolio project.

## What it does
This project measures how NYC weather affects Citibike ridership — turning raw trip and weather data into a clear signal.

## Stack
- Python · pandas (data ingest)
- Web APIs / JSON (data ingest)
- Streamlit on Cloud Run (public dashboard)
- Google BigQuery (data warehouse)

## Pipeline
1. Ingest ~13 yrs of public Citibike trips + weather
2. ETL → load into BigQuery
3. Analyze how weather moves ridership
4. Serve a public Streamlit dashboard

## Dashboard
link coming once deployed.

## Status
🚧 In progress
