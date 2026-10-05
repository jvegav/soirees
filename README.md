# Lyon Nightlife ETL

An Airflow ETL project for finding restaurants that are likely to be open after leaving a club in Lyon.

## Stack

- Apache Airflow for orchestration
- PostgreSQL + PostGIS for the warehouse
- Python, pandas and SQLAlchemy
- FastAPI backend for serving PostGIS data
- Angular + Leaflet dashboard
- OpenStreetMap/Overpass as the default source
- Optional DATAtourisme and SIRENE enrichment

## Quick start

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start the stack:

   ```bash
   docker compose up airflow-init
   docker compose up -d
   ```

3. Open Airflow at http://localhost:8080 (`airflow` / `airflow`).
4. Enable and trigger `lyon_nightlife_etl`.
5. Connect to the warehouse at `postgresql://lyon:lyon@localhost:5433/lyon_nightlife`.

The default DAG extracts Lyon venues from OpenStreetMap through Overpass, normalizes them, deduplicates records, and loads them into PostGIS. DATAtourisme and SIRENE are disabled unless configured.

## Project layout

```text
airflow/dags/                 Airflow DAGs
airflow/plugins/              Reusable ETL code
sql/                          Warehouse schema and recommendation views
data/raw/                     Local raw downloads (gitignored)
requirements.txt              Python dependencies
docker-compose.yml            Local Airflow + PostGIS stack
```

## Data notes

- OSM data is licensed under ODbL. Keep attribution in any published dashboard.
- Opening hours are estimates and may be missing or stale.
- The parser handles cross-midnight intervals such as `18:00-04:00`.
- DATAtourisme requires an API key.
- SIRENE is a large download; configure a suitable Lyon extract before enabling it.

## Run the dashboard

Start the warehouse and API/dashboard services:

```bash
docker compose up -d warehouse api dashboard
```

Open the dashboard at http://localhost:4200. The API is available at http://localhost:8000/docs and the database remains available at `localhost:5433`.

Run Airflow separately when you want to refresh the data:

```bash
docker compose up airflow-init
docker compose up -d airflow-webserver airflow-scheduler
```

Then open http://localhost:8080 and trigger `lyon_nightlife_etl`. Refresh the Angular dashboard when the DAG completes.

For local Angular development without Docker:

```bash
cd frontend
npm install
npm start
```

The developmehttp://localhost:4200/nt server expects the API at `/api`; use the Docker dashboard for the simplest setup because its Nginx configuration proxies `/api` to FastAPI.
