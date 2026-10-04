CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS raw.venues (
    raw_id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT,
    category TEXT,
    address TEXT,
    postcode TEXT,
    city TEXT,
    phone TEXT,
    website TEXT,
    opening_hours TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    tags JSONB,
    source_updated_at TIMESTAMPTZ,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS core.places (
    place_id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('restaurant', 'bar', 'club', 'cafe', 'other')),
    address TEXT,
    postcode TEXT,
    city TEXT,
    phone TEXT,
    website TEXT,
    opening_hours TEXT,
    source_count INTEGER NOT NULL DEFAULT 1,
    data_quality_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom geometry(Point, 4326) NOT NULL,
    source_updated_at TIMESTAMPTZ,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(canonical_name, latitude, longitude)
);
CREATE INDEX IF NOT EXISTS places_geom_idx ON core.places USING GIST (geom);
CREATE INDEX IF NOT EXISTS places_category_idx ON core.places(category);

CREATE TABLE IF NOT EXISTS analytics.routes (
    route_id BIGSERIAL PRIMARY KEY,
    club_id BIGINT NOT NULL REFERENCES core.places(place_id),
    restaurant_id BIGINT NOT NULL REFERENCES core.places(place_id),
    mode TEXT NOT NULL DEFAULT 'walking',
    distance_meters INTEGER,
    duration_minutes NUMERIC(8,2),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(club_id, restaurant_id, mode)
);

CREATE OR REPLACE VIEW analytics.open_late_candidates AS
SELECT c.place_id AS club_id, c.canonical_name AS club_name,
       r.place_id AS restaurant_id, r.canonical_name AS restaurant_name,
       r.address AS restaurant_address, r.opening_hours,
       r.data_quality_score,
       ST_Distance(c.geom::geography, r.geom::geography)::INTEGER AS straight_line_distance_meters
FROM core.places c
JOIN core.places r ON r.category = 'restaurant'
WHERE c.category = 'club' AND c.place_id <> r.place_id
  AND ST_DWithin(c.geom::geography, r.geom::geography, 3000);
