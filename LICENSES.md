# Licenses of what this repository uses

Every external source, the terms it comes under, and the date those terms were
read. This project is individual academic coursework for *Dealing With Data*,
NYU Stern MSBAi, July 2026. It is not a commercial product and the data is not
sold.

| source | what is used | terms | read on |
|---|---|---|---|
| Citi Bike system data, public archive at `s3.amazonaws.com/tripdata` | 169 zip files, 2013-06 to 2026-05, ingested into BigQuery; only a daily summary (8,634 rows) is committed | Citi Bike Data License Agreement (Lyft Bikes and Scooters, LLC): permits access, reproduction, analysis, modification and distribution in a product or service for any lawful purpose; prohibits selling the dataset on its own, correlating it with customer identities, and using Citi Bike or Lyft trademarks. This repository names the dataset and uses no marks. Data is provided as is | 2026-09-20 |
| NOAA GHCN-Daily, via `bigquery-public-data.ghcn_d`, station USW00094728 (Central Park) | daily TMAX, TMIN, PRCP, SNOW joined onto NYC rows | Work of the US federal government, public domain; NOAA asks for citation of GHCN-Daily. Accessed through Google's BigQuery public datasets programme | 2026-09-20 |
| Google BigQuery public datasets | hosting of the GHCN copy | Google Cloud terms; the data itself keeps its original public-domain status | 2026-09-20 |

Code in this repository: MIT, see `LICENSE`.

No personal data: the legacy schema's birth year and gender columns are carried
through the clean view and never analysed, and the committed bundle holds daily
aggregates only.
