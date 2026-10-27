# Lyon Nightlife Data Platform

> An end-to-end Data Engineering project that helps people find restaurants that are likely to be open after leaving a nightclub in Lyon, France.

[![Airflow](https://img.shields.io/badge/orchestration-Apache%20Airflow-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![PostGIS](https://img.shields.io/badge/warehouse-PostgreSQL%20%2B%20PostGIS-336791?logo=postgresql&logoColor=white)](https://postgis.net/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Angular](https://img.shields.io/badge/frontend-Angular-DD0031?logo=angular&logoColor=white)](https://angular.dev/)
[![Docker](https://img.shields.io/badge/runtime-Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

## Project overview

This personal project was built to demonstrate a complete, reproducible data product rather than an isolated script. It combines public geospatial data, an orchestrated ETL pipeline, a spatial warehouse and a consumer-facing dashboard.

The product answers a practical question:

> **After leaving a club in Lyon, which nearby restaurants can I reach on foot and which ones are likely to be open at the time I want to go?**

The pipeline extracts restaurants, bars, cafés and clubs from OpenStreetMap through Overpass, optionally enriches the dataset with DATAtourisme and SIRENE, creates canonical place records in PostgreSQL/PostGIS, calculates spatial candidates and exposes them through a FastAPI service. An Angular/Leaflet dashboard lets users explore the results by club, distance, time and current location.

## What this project demonstrates

- Designing a batch ETL pipeline with Apache Airflow and task dependencies.
- Working with semi-structured source data and normalizing it into a shared schema.
- Preserving raw data and source provenance before applying transformations.
- Deduplicating entities from multiple sources using name, category and coordinates.
- Modeling and querying geospatial data with PostgreSQL/PostGIS.
- Building derived analytics: distance, estimated walking time and opening-status ranking.
- Serving data through a documented REST API with pagination and filters.
- Building a usable data application with Angular and Leaflet.
- Protecting an external API with a database-backed one-request-per-day cache.
- Reproducing the whole stack locally with Docker Compose.

## Architecture

![Platform architecture](docs/diagrams/architecture.svg)

### Main components

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Sources | OpenStreetMap / Overpass | Primary venue discovery for the Lyon bounding box |
| Optional sources | DATAtourisme, SIRENE | Additional tourism or company data when configured |
| Orchestration | Apache Airflow | Scheduling, dependencies, retries and observability |
| Transformation | Python, SQLAlchemy, requests | Extraction, normalization, upsert and canonicalization |
| Warehouse | PostgreSQL 16 + PostGIS | Raw, core and analytics schemas; spatial indexing and distance queries |
| Serving | FastAPI + psycopg2 | REST endpoints for summaries, clubs and recommendations |
| Frontend | Angular 19 + Leaflet | Interactive map, filters, opening status and pagination |
| Runtime | Docker Compose | Reproducible local development environment |

## ETL pipeline

![ETL pipeline](docs/diagrams/etl-pipeline.svg)

The Airflow DAG is called `lyon_nightlife_etl` and runs daily with `catchup=False`:

```text
extract_osm ───────────────┐
extract_datatourisme ──────┼──> load_raw_and_normalize
extract_sirene ────────────┘             │
                                        v
                              transform_core_places
                                        │
                                        v
                             calculate_walking_candidates
```

### Pipeline stages

1. **Extract**: query Overpass for `restaurant`, `bar`, `pub`, `nightclub` and `cafe` amenities inside `LYON_BBOX`.
2. **Normalize**: map source-specific fields to a common venue contract, standardize categories and preserve original tags as JSONB.
3. **Load raw**: upsert into `raw.venues` using `(source, source_id)` as the natural key. Re-running the extraction does not create duplicate raw records.
4. **Transform core**: aggregate records into `core.places`, calculate a data quality score and create PostGIS points with SRID 4326.
5. **Calculate analytics**: generate club-to-restaurant candidates within 3 km and calculate geodesic distance using PostGIS geography operations.
6. **Serve**: the API ranks candidates by opening status, distance and data quality for the Angular dashboard.

The transformation clears derived routes before rebuilding canonical places because `analytics.routes` has foreign keys referencing `core.places`. This keeps a full refresh consistent without violating referential integrity.

## Warehouse model

![Warehouse data model](docs/diagrams/data-model.svg)

The database is organized into three logical layers:

- **`raw.venues`**: source-aligned records, original identifiers, extracted timestamps and JSONB tags.
- **`core.places`**: canonical restaurants, bars, cafés and clubs used by the product.
- **`analytics.routes`**: derived club-to-restaurant candidates with distance and estimated walking duration.
- **Google cache tables**: `analytics.google_daily_requests` records the daily request and `analytics.google_places` stores returned places and opening information.

Important design choices:

- PostGIS `geometry(Point, 4326)` plus a GiST index supports spatial filtering.
- Distances are calculated on `geography`, so results are expressed in meters.
- Source count, opening hours and address completeness contribute to `data_quality_score`.
- Raw and derived layers are separated so the pipeline remains auditable and rebuildable.

## Recommendation logic

The API endpoint `/api/recommendations` supports:

- Club origin or browser geolocation (`origin_lat`, `origin_lon`).
- Maximum distance from 250 m to 10 km.
- Visit time in `HH:MM` format.
- `open_only=true` to keep only restaurants open by schedule or confirmed open by Google.
- Pagination with a default page size of 10.

Opening status is intentionally transparent:

| Status | Meaning |
| --- | --- |
| `open_confirmed` | Google Places reported the venue as open |
| `closed_confirmed` | Google Places reported the venue as closed |
| `open_by_schedule` | Source opening hours match the selected time |
| `closed_by_schedule` | Parsed opening hours do not match the selected time |
| `hours_available` | Opening hours exist but no specific time was selected |
| `unknown` | There is not enough information to make a reliable claim |

Google Places is deliberately protected by a database-backed daily cache. At most one request is made per Paris calendar day; when Google is unavailable, the product falls back to OSM/DATAtourisme information instead of failing the dashboard.

## Quick start

### Prerequisites

- Docker Engine and Docker Compose v2.
- At least 4 GB of available memory for the local Airflow stack.
- A Google Places API key is optional. The core ETL works with OpenStreetMap alone.

### 1. Configure environment variables

```bash
cp .env.example .env
```

The main variables are:

```dotenv
OVERPASS_URL=https://overpass-api.de/api/interpreter
LYON_BBOX=45.68,4.75,45.85,4.95

# Optional enrichment
DATATOURISME_URL=
DATATOURISME_API_KEY=
SIRENE_URL=

# Optional dashboard enrichment; never commit the real key
GOOGLE_MAPS_API_KEY=
```

### 2. Start the stack

```bash
docker compose up airflow-init
docker compose up -d
```

Services:

| Service | URL |
| --- | --- |
| Angular dashboard | http://localhost:4200 |
| FastAPI Swagger UI | http://localhost:8000/docs |
| FastAPI health check | http://localhost:8000/health |
| Airflow UI | http://localhost:8080 |
| PostgreSQL/PostGIS | `postgresql://lyon:lyon@localhost:5433/lyon_nightlife` |

Airflow credentials in this local setup are `airflow` / `airflow`.

### 3. Run the ETL

Open Airflow, enable `lyon_nightlife_etl` and trigger it manually. Or trigger it from the terminal:

```bash
docker compose exec airflow-webserver airflow dags trigger lyon_nightlife_etl
```

Check task logs in Airflow in this order:

```text
extract_osm
load_raw_and_normalize
transform_core_places
calculate_walking_candidates
```

### 4. Validate the warehouse

```bash
docker exec lyon-nightlife-warehouse \
  psql -U lyon -d lyon_nightlife \
  -c "SELECT category, COUNT(*) FROM core.places GROUP BY category ORDER BY category;"
```

```bash
docker exec lyon-nightlife-warehouse \
  psql -U lyon -d lyon_nightlife \
  -c "SELECT COUNT(*) AS walking_candidates FROM analytics.routes;"
```

After the DAG succeeds, refresh http://localhost:4200.

## API examples

List clubs:

```bash
curl http://localhost:8000/api/clubs
```

Get the first 10 restaurants near a club, filtered for 23:00:

```bash
curl "http://localhost:8000/api/recommendations?club_id=12760&visit_time=23:00&page=1&page_size=10&max_distance_meters=3000"
```

Use a location instead of a club:

```bash
curl "http://localhost:8000/api/recommendations?origin_lat=45.7640&origin_lon=4.8357&visit_time=23:00&open_only=true"
```

## Project structure

```text
.
├── airflow/
│   ├── dags/lyon_nightlife_etl.py       # DAG and task dependencies
│   └── plugins/lyon_etl.py              # Extraction, normalization and transforms
├── backend/
│   ├── app.py                           # FastAPI endpoints and Google cache
│   └── requirements.txt
├── frontend/
│   ├── src/app/                         # Angular dashboard and Leaflet map
│   └── nginx.conf                       # API reverse proxy in production build
├── sql/
│   ├── init.sql                         # Warehouse schemas and tables
│   └── migrations/                      # Incremental schema changes
├── docs/diagrams/                       # Versioned architecture diagrams
├── data/raw/                            # Local extraction files, not committed
├── docker-compose.yml
└── requirements.txt
```

## Data quality, limitations and responsible use

- OpenStreetMap coverage and opening hours are community-maintained and can be incomplete or stale.
- Walking duration is an estimate based on distance and an average speed; it is not turn-by-turn routing.
- The current opening-hours parser handles common time intervals and overnight ranges, but complex OSM conditional syntax may be classified as `unknown`.
- Google Places is an enrichment layer, not the source of truth for the ETL. Its API key must stay out of Git and its terms and quotas must be respected.
- OSM data is licensed under ODbL. Any public deployment must keep the appropriate OpenStreetMap attribution.
- Location access is requested only by the browser when the user selects “Use my current location”.

## Engineering decisions and future improvements

This project is intentionally designed as a portfolio foundation. Possible next iterations include:

- Add automated tests for normalization, opening-hours parsing and API contracts.
- Add Great Expectations or dbt tests for freshness, uniqueness, null rates and spatial validity.
- Replace straight-line walking estimates with an OpenRouteService or OSRM routing stage.
- Add incremental extraction based on source timestamps and a proper backfill strategy.
- Add CI with linting, unit tests, frontend build and Docker image checks.
- Add observability with Airflow metrics, structured logs and data freshness indicators.
- Use a dedicated geocoding/entity-resolution step for stronger cross-source deduplication.
- Deploy the warehouse, API and dashboard to a cloud environment with secrets management.

## Resume-ready summary

Designed and implemented an end-to-end geospatial data platform for Lyon nightlife using Apache Airflow, Python, PostgreSQL/PostGIS, FastAPI and Angular. Built an orchestrated ETL pipeline with raw-layer provenance, normalization, deduplication, spatial analytics, opening-hours classification, API pagination and a daily Google Places cache. Delivered an interactive dashboard that recommends nearby restaurants based on club location, distance, visit time and availability.

## License and attribution

This repository is a personal portfolio project. Source data from OpenStreetMap must be attributed to **© OpenStreetMap contributors** and used according to the [ODbL](https://www.openstreetmap.org/copyright).
