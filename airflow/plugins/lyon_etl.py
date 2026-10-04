"""Small, dependency-light extraction and loading helpers for the Lyon ETL."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import create_engine, text

RAW_DIR = Path(os.getenv("RAW_DATA_DIR", "/opt/airflow/data/raw"))
RAW_DIR.mkdir(parents=True, exist_ok=True)


def bbox() -> tuple[str, str, str, str]:
    values = os.getenv("LYON_BBOX", "45.68,4.75,45.85,4.95").split(",")
    if len(values) != 4:
        raise ValueError("LYON_BBOX must be south,west,north,east")
    return tuple(values)  # type: ignore[return-value]


def extract_osm() -> str:
    south, west, north, east = bbox()
    query = f"""
    [out:json][timeout:90];
    (
      nwr["amenity"~"restaurant|bar|pub|nightclub|cafe"]({south},{west},{north},{east});
    );
    out center tags;
    """
    response = requests.post(
        os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter"),
        data=query,
        timeout=120,
        headers={"User-Agent": "lyon-nightlife-etl/0.1"},
    )
    response.raise_for_status()
    path = RAW_DIR / "osm.json"
    path.write_text(response.text, encoding="utf-8")
    return str(path)


def extract_datatourisme() -> str | None:
    url = os.getenv("DATATOURISME_URL")
    key = os.getenv("DATATOURISME_API_KEY")
    if not url or not key:
        return None
    response = requests.get(
        url,
        headers={"X-API-Key": key, "User-Agent": "lyon-nightlife-etl/0.1"},
        params={"geo_distance": "45.7640,4.8357,15km", "page_size": 1000},
        timeout=60,
    )
    response.raise_for_status()
    path = RAW_DIR / "datatourisme.json"
    path.write_text(response.text, encoding="utf-8")
    return str(path)


def extract_sirene() -> str | None:
    url = os.getenv("SIRENE_URL")
    if not url:
        return None
    response = requests.get(url, timeout=180, headers={"User-Agent": "lyon-nightlife-etl/0.1"})
    response.raise_for_status()
    path = RAW_DIR / "sirene.csv"
    path.write_bytes(response.content)
    return str(path)


def _osm_category(tags: dict[str, Any]) -> str:
    value = tags.get("amenity", "other")
    return {"restaurant": "restaurant", "bar": "bar", "pub": "bar", "nightclub": "club", "cafe": "cafe"}.get(value, "other")


def _normalise_hours(value: Any) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", str(value))


def normalise_osm(path: str) -> list[dict[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    extracted_at = datetime.now(timezone.utc).isoformat()
    records = []
    for element in document.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center", {})
        latitude = element.get("lat", center.get("lat"))
        longitude = element.get("lon", center.get("lon"))
        if not tags.get("name") or latitude is None or longitude is None:
            continue
        records.append({
            "source": "osm",
            "source_id": str(element["id"]),
            "name": tags.get("name"),
            "category": _osm_category(tags),
            "address": " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")])),
            "postcode": tags.get("addr:postcode"),
            "city": tags.get("addr:city", "Lyon"),
            "phone": tags.get("phone"),
            "website": tags.get("website"),
            "opening_hours": _normalise_hours(tags.get("opening_hours")),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "tags": tags,
            "source_updated_at": None,
            "extracted_at": extracted_at,
        })
    return records


def normalise_datatourisme(path: str) -> list[dict[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    objects = document.get("objects", document if isinstance(document, list) else [])
    records = []
    for item in objects:
        location = item.get("isLocatedAt", {})
        address = location.get("address", {}) if isinstance(location, dict) else {}
        coordinates = location.get("geometry", {}).get("coordinates", []) if isinstance(location, dict) else []
        if len(coordinates) != 2 or not item.get("label"):
            continue
        raw_type = str(item.get("type", "Restaurant")).lower()
        category = "club" if "nightclub" in raw_type or "discotheque" in raw_type else "restaurant" if "restaurant" in raw_type else "other"
        records.append({
            "source": "datatourisme",
            "source_id": str(item.get("id", item.get("uuid"))),
            "name": item.get("label"),
            "category": category,
            "address": address.get("streetAddress"),
            "postcode": address.get("postalCode"),
            "city": address.get("addressLocality", "Lyon"),
            "phone": None,
            "website": None,
            "opening_hours": None,
            "latitude": float(coordinates[1]),
            "longitude": float(coordinates[0]),
            "tags": item,
            "source_updated_at": item.get("lastUpdate"),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        })
    return records


def load_records(records: list[dict[str, Any]], connection_uri: str) -> int:
    engine = create_engine(connection_uri)
    sql = text("""
        INSERT INTO raw.venues
        (source, source_id, name, category, address, postcode, city, phone, website,
         opening_hours, latitude, longitude, tags, source_updated_at, extracted_at)
        VALUES (:source, :source_id, :name, :category, :address, :postcode, :city,
                :phone, :website, :opening_hours, :latitude, :longitude,
                CAST(:tags AS jsonb), :source_updated_at, :extracted_at)
        ON CONFLICT (source, source_id) DO UPDATE SET
          name = EXCLUDED.name, category = EXCLUDED.category, address = EXCLUDED.address,
          opening_hours = EXCLUDED.opening_hours, latitude = EXCLUDED.latitude,
          longitude = EXCLUDED.longitude, tags = EXCLUDED.tags,
          extracted_at = EXCLUDED.extracted_at
    """)
    with engine.begin() as connection:
        connection.execute(sql, [{**record, "tags": json.dumps(record.get("tags", {}))} for record in records])
    return len(records)


def transform_core(connection_uri: str) -> None:
    engine = create_engine(connection_uri)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM core.places"))
        connection.execute(text("""
            INSERT INTO core.places
            (canonical_name, category, address, postcode, city, phone, website,
             opening_hours, source_count, data_quality_score, latitude, longitude,
             geom, source_updated_at)
            SELECT name, category, MAX(address), MAX(postcode), MAX(city), MAX(phone), MAX(website),
                   MAX(opening_hours), COUNT(DISTINCT source),
                   LEAST(100, 30 + COUNT(DISTINCT source) * 20
                     + CASE WHEN MAX(opening_hours) IS NOT NULL THEN 20 ELSE 0 END
                     + CASE WHEN MAX(address) IS NOT NULL THEN 10 ELSE 0 END),
                   AVG(latitude), AVG(longitude),
                   ST_SetSRID(ST_MakePoint(AVG(longitude), AVG(latitude)), 4326),
                   MAX(source_updated_at)
            FROM raw.venues
            WHERE name IS NOT NULL AND latitude BETWEEN 45 AND 46 AND longitude BETWEEN 4 AND 5
            GROUP BY LOWER(TRIM(name)), category, ROUND(latitude::numeric, 4), ROUND(longitude::numeric, 4)
        """))


def calculate_routes(connection_uri: str) -> None:
    engine = create_engine(connection_uri)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO analytics.routes (club_id, restaurant_id, distance_meters, duration_minutes)
            SELECT c.place_id, r.place_id,
                   ST_Distance(c.geom::geography, r.geom::geography)::INTEGER,
                   ROUND((ST_Distance(c.geom::geography, r.geom::geography) / 80.0)::numeric, 2)
            FROM core.places c CROSS JOIN core.places r
            WHERE c.category = 'club' AND r.category = 'restaurant'
              AND c.place_id <> r.place_id
              AND ST_DWithin(c.geom::geography, r.geom::geography, 3000)
            ON CONFLICT (club_id, restaurant_id, mode) DO UPDATE SET
              distance_meters = EXCLUDED.distance_meters,
              duration_minutes = EXCLUDED.duration_minutes,
              calculated_at = now()
        """))
