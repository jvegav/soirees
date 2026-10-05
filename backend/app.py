from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import Json, RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lyon:lyon@localhost:5433/lyon_nightlife")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
PARIS_TZ = ZoneInfo("Europe/Paris")
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


def google_refresh_once_per_day(latitude: float, longitude: float) -> None:
    """Refresh Google Places at most once per Paris calendar day globally."""
    if not GOOGLE_MAPS_API_KEY:
        return
    today = datetime.now(PARIS_TZ).date()
    with connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT 1 FROM analytics.google_daily_requests WHERE request_date = %s", (today,))
            if cursor.fetchone():
                return

            response = requests.post(
                "https://places.googleapis.com/v1/places:searchNearby",
                headers={
                    "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
                    "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.currentOpeningHours,places.googleMapsUri",
                    "Content-Type": "application/json",
                },
                json={
                    "includedTypes": ["restaurant"],
                    "maxResultCount": 20,
                    "locationRestriction": {
                        "circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": 3000}
                    },
                },
                timeout=20,
            )
            try:
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                # Consume today's single attempt and keep the dashboard usable
                # with OSM/DATAtourisme data when Google is misconfigured.
                payload = {"error": "Google Places request failed", "status_code": response.status_code}
                cursor.execute(
                    "INSERT INTO analytics.google_daily_requests (request_date, origin_latitude, origin_longitude, response_json) VALUES (%s, %s, %s, %s)",
                    (today, latitude, longitude, Json(payload)),
                )
                conn.commit()
                return
            cursor.execute(
                "INSERT INTO analytics.google_daily_requests (request_date, origin_latitude, origin_longitude, response_json) VALUES (%s, %s, %s, %s)",
                (today, latitude, longitude, Json(payload)),
            )
            for place in payload.get("places", []):
                location = place.get("location", {})
                opening = place.get("currentOpeningHours", {})
                cursor.execute("""
                    INSERT INTO analytics.google_places
                    (google_place_id, name, latitude, longitude, open_now, current_opening_hours, maps_uri, checked_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (google_place_id) DO UPDATE SET
                      name = EXCLUDED.name, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
                      open_now = EXCLUDED.open_now, current_opening_hours = EXCLUDED.current_opening_hours,
                      maps_uri = EXCLUDED.maps_uri, checked_date = EXCLUDED.checked_date, checked_at = now()
                """, (
                    place.get("id"), place.get("displayName", {}).get("text"),
                    location.get("latitude"), location.get("longitude"), opening.get("openNow"),
                    Json(opening) if opening else None, place.get("googleMapsUri"), today,
                ))
        conn.commit()


def schedule_status(opening_hours: str | None, visit_time: str | None) -> str:
    if not visit_time:
        return "hours_available" if opening_hours else "unknown"
    if not opening_hours:
        return "unknown"
    if "24/7" in opening_hours.replace(" ", ""):
        return "open_by_schedule"
    try:
        target = int(visit_time[:2]) * 60 + int(visit_time[3:])
    except (ValueError, IndexError):
        return "unknown"
    found_range = False
    for start, end in re.findall(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", opening_hours):
        found_range = True
        start_min = int(start.split(":")[0]) * 60 + int(start.split(":")[1])
        end_min = int(end.split(":")[0]) * 60 + int(end.split(":")[1])
        is_open = start_min <= target <= end_min if end_min >= start_min else target >= start_min or target <= end_min
        if is_open:
            return "open_by_schedule"
    return "closed_by_schedule" if found_range else "unknown"

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
def recommendations(
    club_id: int | None = Query(default=None),
    origin_lat: float | None = Query(default=None, ge=45, le=46),
    origin_lon: float | None = Query(default=None, ge=4, le=5),
    max_distance_meters: int = Query(default=3000, ge=250, le=10000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    visit_time: str | None = Query(default=None, pattern=r"^\d{2}:\d{2}$"),
    open_only: bool = Query(default=False),
) -> dict[str, Any]:
    if origin_lat is not None and origin_lon is not None:
        google_refresh_once_per_day(origin_lat, origin_lon)
        origin_cte = "SELECT NULL::bigint AS place_id, %s::double precision AS latitude, %s::double precision AS longitude, 'My location'::text AS name"
        origin_params: list[Any] = [origin_lat, origin_lon]
    else:
        if club_id is not None:
            club = fetch_all("SELECT place_id, latitude, longitude FROM core.places WHERE place_id = %s AND category = 'club'", (club_id,))
            if club:
                google_refresh_once_per_day(club[0]["latitude"], club[0]["longitude"])
            origin_cte = "SELECT c.place_id, c.latitude, c.longitude, c.canonical_name AS name FROM core.places c WHERE c.place_id = %s"
            origin_params = [club_id]
        else:
            google_refresh_once_per_day(45.7640, 4.8357)
            origin_cte = "SELECT c.place_id, c.latitude, c.longitude, c.canonical_name AS name FROM core.places c WHERE c.category = 'club'"
            origin_params = []

    params: list[Any] = origin_params + [max_distance_meters]
    origin_sql = f"WITH origin AS ({origin_cte})"
    items = fetch_all(f"""
        {origin_sql}
        SELECT o.place_id AS club_id, o.name AS club_name,
               r.place_id AS restaurant_id, r.canonical_name AS restaurant_name,
               r.address AS restaurant_address, r.opening_hours,
               r.data_quality_score::float, r.latitude, r.longitude,
               gp.open_now AS google_open_now, gp.maps_uri AS google_maps_uri,
               CASE WHEN gp.open_now IS TRUE THEN 'open_confirmed' WHEN gp.open_now IS FALSE THEN 'closed_confirmed' WHEN r.opening_hours IS NOT NULL THEN 'hours_available' ELSE 'unknown' END AS open_status,
               ST_Distance(ST_SetSRID(ST_MakePoint(o.longitude, o.latitude), 4326)::geography, r.geom::geography)::int AS distance_meters,
               ROUND((ST_Distance(ST_SetSRID(ST_MakePoint(o.longitude, o.latitude), 4326)::geography, r.geom::geography) / 80.0)::numeric, 1)::float AS walking_minutes
        FROM origin o CROSS JOIN core.places r
        LEFT JOIN LATERAL (
          SELECT open_now, maps_uri
          FROM analytics.google_places g
          WHERE ST_DWithin(ST_SetSRID(ST_MakePoint(g.longitude, g.latitude), 4326)::geography, r.geom::geography, 150)
          ORDER BY ST_Distance(ST_SetSRID(ST_MakePoint(g.longitude, g.latitude), 4326)::geography, r.geom::geography)
          LIMIT 1
        ) gp ON TRUE
        WHERE r.category = 'restaurant'
          AND ST_DWithin(ST_SetSRID(ST_MakePoint(o.longitude, o.latitude), 4326)::geography, r.geom::geography, %s)
        ORDER BY distance_meters, r.data_quality_score DESC, r.canonical_name
    """, tuple(params))
    for item in items:
        if visit_time:
            item["open_status"] = schedule_status(item["opening_hours"], visit_time)
    if open_only:
        items = [item for item in items if item["open_status"] in ("open_confirmed", "open_by_schedule")]
    priority = {"open_confirmed": 0, "open_by_schedule": 0, "hours_available": 1, "unknown": 2, "closed_confirmed": 3, "closed_by_schedule": 3}
    items.sort(key=lambda item: (priority.get(item["open_status"], 2), item["distance_meters"], -(item["data_quality_score"] or 0), item["restaurant_name"]))
    total = len(items)
    offset = (page - 1) * page_size
    items = items[offset:offset + page_size]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }
