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
    name            TEXT NOT NULL UNIQUE,
    county          TEXT,
    code            TEXT UNIQUE,                     -- the model's name for the catchment
    geom            GEOMETRY(Point, 4326) NOT NULL,  -- map marker point
    boundary        GEOMETRY(Polygon, 4326),         -- delineated catchment shape
    is_active       BOOLEAN NOT NULL DEFAULT true,   -- inactive catchments are kept, not deleted
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
    -- Rolling features the simulated feed already publishes alongside
    -- the raw readings above (see ingestion/config.py's FEATURE_FIELDS).
    -- Stored here too so live model scoring (ingestion/model_scoring.py)
    -- can read a catchment's full feature history straight back out of
    -- this table, rather than recomputing rolling sums/diffs itself.
    rainfall_3day       DOUBLE PRECISION,
    rainfall_7day       DOUBLE PRECISION,
    discharge_change    DOUBLE PRECISION,
    imerg_max_rate      DOUBLE PRECISION,
    imerg_total_mm      DOUBLE PRECISION,
    imerg_hours_ge5     DOUBLE PRECISION,
    era5_rain_mm        DOUBLE PRECISION,
    soil_1              DOUBLE PRECISION,
    soil_2              DOUBLE PRECISION,
    temp_c              DOUBLE PRECISION,
    dewpoint_depression DOUBLE PRECISION,
    pressure_hpa        DOUBLE PRECISION,
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
    status                  TEXT NOT NULL DEFAULT 'active',  -- 'active', 'acknowledged', 'resolved'
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Who moved the alert on and when (Emergency Responders only)
    acknowledged_at         TIMESTAMPTZ,
    acknowledged_by         TEXT,
    resolved_at             TIMESTAMPTZ,
    resolved_by             TEXT
);
CREATE INDEX idx_alerts_catchment_status ON alerts (catchment_id, status);

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,   -- actor roles per Chapter 3 use case diagram
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Two-factor authentication (TOTP), beyond what the proposal asked
    -- for. totp_secret is NULL until a user enrols; totp_enabled stays
    -- false until they confirm their first code, so a half-finished
    -- enrolment never locks anyone out (see backend/routes_auth.py).
    totp_secret     TEXT,
    totp_enabled    BOOLEAN NOT NULL DEFAULT false,
    -- Google Sign-In (also beyond the proposal). NULL until an admin
    -- attaches a Gmail address to this already-provisioned account;
    -- POST /login/google only succeeds for an email that matches here,
    -- so this never opens the door to public self-registration.
    email           TEXT UNIQUE
);

-- System Administration screen's log panel (proposal 3.4.6). One row
-- per notable event (sign-ins, account changes); actor is a username,
-- null for an attempt that never resolved to a real account (e.g. a
-- login for an unknown username).
CREATE TABLE system_logs (
    id              BIGSERIAL PRIMARY KEY,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor           TEXT,
    action          TEXT NOT NULL,
    detail          TEXT
);
CREATE INDEX idx_system_logs_occurred_at ON system_logs (occurred_at DESC);
