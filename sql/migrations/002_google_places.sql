CREATE TABLE IF NOT EXISTS analytics.google_daily_requests (
    request_date DATE PRIMARY KEY,
    origin_latitude DOUBLE PRECISION NOT NULL,
    origin_longitude DOUBLE PRECISION NOT NULL,
    response_json JSONB NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.google_places (
    google_place_id TEXT PRIMARY KEY,
    name TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    open_now BOOLEAN,
    current_opening_hours JSONB,
    maps_uri TEXT,
    checked_date DATE NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
