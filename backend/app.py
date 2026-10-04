from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import psycopg2
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lyon:lyon@localhost:5433/lyon_nightlife")
app = FastAPI(title="Lyon Nightlife API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"], allow_credentials=True, allow_methods=["GET"], allow_headers=["*"])

@contextmanager
def connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

@app.get("/health")
def health() -> dict[str, str]:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    return {"status": "ok"}

@app.get("/api/summary")
def summary() -> dict[str, int]:
    rows = fetch_all("SELECT category, COUNT(*)::int AS count FROM core.places GROUP BY category")
    result = {"total": 0, "restaurants": 0, "clubs": 0, "bars": 0, "cafes": 0}
    for row in rows:
        key = {"restaurant": "restaurants", "club": "clubs", "bar": "bars", "cafe": "cafes"}.get(row["category"])
        if key:
            result[key] = row["count"]
        result["total"] += row["count"]
    return result

@app.get("/api/clubs")
def clubs() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT place_id AS id, canonical_name AS name, address, latitude, longitude, opening_hours
        FROM core.places WHERE category = 'club' ORDER BY canonical_name
    """)

@app.get("/api/recommendations")
def recommendations(club_id: int | None = Query(default=None), max_distance_meters: int = Query(default=3000, ge=250, le=10000)) -> list[dict[str, Any]]:
    params: list[Any] = [max_distance_meters]
    club_filter = ""
    if club_id is not None:
        club_filter = "AND c.place_id = %s"
        params.append(club_id)
    return fetch_all(f"""
        SELECT c.place_id AS club_id, c.canonical_name AS club_name,
               r.place_id AS restaurant_id, r.canonical_name AS restaurant_name,
               r.address AS restaurant_address, r.opening_hours,
               r.data_quality_score::float, r.latitude, r.longitude,
               ST_Distance(c.geom::geography, r.geom::geography)::int AS distance_meters,
               ROUND((ST_Distance(c.geom::geography, r.geom::geography) / 80.0)::numeric, 1)::float AS walking_minutes
        FROM core.places c JOIN core.places r ON r.category = 'restaurant'
        WHERE c.category = 'club' AND c.place_id <> r.place_id
          AND ST_DWithin(c.geom::geography, r.geom::geography, %s) {club_filter}
        ORDER BY distance_meters, r.data_quality_score DESC, r.canonical_name LIMIT 100
    """, tuple(params))
