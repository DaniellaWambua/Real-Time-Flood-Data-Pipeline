-- Schema per proposal section 3.4.4 (Database Schema) and 3.4.3 (ERD).

CREATE TABLE data_sources (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,       -- e.g. 'CHIRPS', 'GloFAS', 'KMD'
    source_type     TEXT NOT NULL,              -- e.g. 'satellite_rainfall', 'hydrological_model', 'advisory'
    fetch_interval  INTERVAL NOT NULL,
    connection_status TEXT NOT NULL DEFAULT 'disconnected',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE catchment_areas (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,       -- matches src/config.py CATCHMENTS entries
    county          TEXT,
    geom            GEOMETRY(Point, 4326) NOT NULL,  -- catchment reference point, 3km-buffered estimate
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_catchment_areas_geom ON catchment_areas USING GIST (geom);

-- Hypertable: one row per timestamped observation per source per catchment.
CREATE TABLE hydro_data_records (
    id              BIGSERIAL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    data_source_id  INTEGER NOT NULL REFERENCES data_sources(id),
    catchment_id    INTEGER NOT NULL REFERENCES catchment_areas(id),
    rainfall_mm         DOUBLE PRECISION,
    river_discharge_m3s DOUBLE PRECISION,
    soil_moisture_m3m3  DOUBLE PRECISION,
    evaporation_mm       DOUBLE PRECISION,
    oni                  DOUBLE PRECISION,
    PRIMARY KEY (id, recorded_at)
);
SELECT create_hypertable('hydro_data_records', 'recorded_at');
CREATE INDEX idx_hydro_data_records_catchment ON hydro_data_records (catchment_id, recorded_at DESC);

-- Hypertable: LSTM inference output per window.
CREATE TABLE anomaly_detection_results (
    id                  BIGSERIAL,
    detected_at         TIMESTAMPTZ NOT NULL,
    catchment_id        INTEGER NOT NULL REFERENCES catchment_areas(id),
    hydro_data_record_id BIGINT,              -- final day's record this score was computed for
    anomaly_score       DOUBLE PRECISION NOT NULL,
    threshold_used       DOUBLE PRECISION NOT NULL,
    is_anomalous         BOOLEAN NOT NULL,
    PRIMARY KEY (id, detected_at)
);
SELECT create_hypertable('anomaly_detection_results', 'detected_at');
CREATE INDEX idx_anomaly_results_catchment ON anomaly_detection_results (catchment_id, detected_at DESC);

CREATE TABLE alerts (
    id                      SERIAL PRIMARY KEY,
    anomaly_detection_result_id BIGINT,
    catchment_id            INTEGER NOT NULL REFERENCES catchment_areas(id),
    severity                TEXT NOT NULL,     -- e.g. 'low', 'medium', 'high'
    status                  TEXT NOT NULL DEFAULT 'active',  -- 'active', 'resolved'
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alerts_catchment_status ON alerts (catchment_id, status);

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,   -- actor roles per Chapter 3 use case diagram
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
