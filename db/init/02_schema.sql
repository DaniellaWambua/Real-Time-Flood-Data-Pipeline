-- Schema per proposal section 3.4.4 (Database Schema) and 3.4.3 (ERD).

CREATE TABLE data_sources (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,       -- the name the producer puts on each message
    source_type     TEXT NOT NULL,              -- e.g. 'daily-feed'
    fetch_interval  INTERVAL NOT NULL,
    connection_status TEXT NOT NULL DEFAULT 'disconnected',
    -- The datasets that arrive through this feed, for the screens to name.
    -- One feed carries all of them: they are combined into one daily reading
    -- per catchment before publishing, not ingested on separate paths.
    datasets        TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,  -- retired sources are kept, not deleted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE catchment_areas (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    county          TEXT,
    code            TEXT UNIQUE,                     -- the model's name for the catchment
    geom            GEOMETRY(Point, 4326) NOT NULL,  -- map marker point
    boundary        GEOMETRY(Polygon, 4326),         -- delineated catchment shape
    wards           TEXT[],                          -- wards mostly inside the catchment (db/add_catchment_wards.py)
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
    model_name          TEXT NOT NULL,        -- e.g. 'lstm_raw v2' or 'lstm_fast v1' (flood_detection.py)
    anomaly_score       DOUBLE PRECISION NOT NULL,
    threshold_used       DOUBLE PRECISION NOT NULL,
    is_anomalous         BOOLEAN NOT NULL,
    PRIMARY KEY (id, detected_at)
);
SELECT create_hypertable('anomaly_detection_results', 'detected_at');
CREATE INDEX idx_anomaly_results_catchment ON anomaly_detection_results (catchment_id, detected_at DESC);

-- A flood incident: consecutive flagged days in one catchment, worked as one case. Each flagged day is
-- still an alert (below), linked to its incident. Disaster Management officers verify or dismiss an
-- incident before responders and officials are told; Emergency Responders acknowledge and resolve it,
-- and on resolving record what they found, which becomes a dated, place-named label for retraining.
CREATE TABLE incidents (
    id                  SERIAL PRIMARY KEY,
    catchment_id        INTEGER NOT NULL REFERENCES catchment_areas(id),
    start_day           DATE NOT NULL,
    end_day             DATE NOT NULL,
    verification        TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'verified', 'dismissed'
    verified_by         TEXT,
    verified_at         TIMESTAMPTZ,
    verification_note   TEXT,
    status              TEXT NOT NULL DEFAULT 'active',   -- 'active', 'acknowledged', 'resolved'
    acknowledged_by     TEXT,
    acknowledged_at     TIMESTAMPTZ,
    resolved_by         TEXT,
    resolved_at         TIMESTAMPTZ,
    outcome             TEXT,      -- on resolving: 'flooding_observed', 'no_flooding' or 'not_checked'
    outcome_places      TEXT,
    outcome_note        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_incidents_catchment_days ON incidents (catchment_id, end_day DESC);

CREATE TABLE alerts (
    id                      SERIAL PRIMARY KEY,
    anomaly_detection_result_id BIGINT,
    catchment_id            INTEGER NOT NULL REFERENCES catchment_areas(id),
    incident_id             INTEGER REFERENCES incidents(id),
    severity                TEXT NOT NULL,     -- e.g. 'low', 'medium', 'high'
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Raised by the fast model before CHIRPS arrives; settled when the full model scores the day
    provisional             BOOLEAN NOT NULL DEFAULT false,
    confirmation            TEXT               -- NULL, 'confirmed' or 'not_confirmed'
);
CREATE INDEX idx_alerts_incident ON alerts (incident_id);

-- What responders and officials did about an incident (use cases "Coordinate field evacuation efforts",
-- "Allocate emergency resources" and "Assist in post-disaster rehabilitation"). kind is 'field'
-- (Emergency Responders), 'resources' (Government Officials) or 'recovery' (either, once resolved).
CREATE TABLE incident_responses (
    id          SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    kind        TEXT NOT NULL,
    note        TEXT NOT NULL,
    author      TEXT NOT NULL,
    author_role TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_incident_responses_incident ON incident_responses (incident_id, created_at);

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT,            -- NULL until an invited user sets a password
    full_name       TEXT,
    organisation    TEXT,
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

-- In-app notifications (the Notifications screen), one row per recipient. read_at is NULL until read.
CREATE TABLE notifications (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    kind        TEXT NOT NULL,    -- 'verify', 'incident', 'update', 'rain'
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    link        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ
);
CREATE INDEX idx_notifications_user ON notifications (user_id, created_at DESC);

-- Browsers and phones that have the installed app's push notifications turned on (Web Push)
CREATE TABLE push_subscriptions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Single-use links emailed for account invites and password resets. Only a SHA-256
-- hash of each link's code is stored, so the table alone cannot be used to sign in.
CREATE TABLE user_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    purpose         TEXT NOT NULL CHECK (purpose IN ('invite', 'reset')),
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_tokens_user ON user_tokens (user_id, purpose);

-- System Administration screen's log panel (proposal 3.4.6). One row
-- per notable event (sign-ins, account changes); actor is a username,
-- null for an attempt that never resolved to a real account (e.g. a
-- login for an unknown username).
CREATE TABLE system_logs (
    id              BIGSERIAL PRIMARY KEY,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor           TEXT,
    action          TEXT NOT NULL,
    detail          TEXT,
    -- Activity log area: 'sign_in', 'accounts', 'alerts' or 'pipeline' (models.log_category)
    category        TEXT NOT NULL DEFAULT 'accounts'
);
CREATE INDEX idx_system_logs_occurred_at ON system_logs (occurred_at DESC);
CREATE INDEX idx_system_logs_category ON system_logs (category, id DESC);

-- Ward boundaries (geoBoundaries, CC BY 4.0), used to name the wards each catchment covers.
CREATE TABLE wards (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    boundary        GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX idx_wards_boundary ON wards USING GIST (boundary);

-- Open-Meteo daily rainfall forecasts per catchment, latest issue kept per day.
-- is_warning marks a forecast at or above the rainfall warning threshold.
CREATE TABLE rainfall_forecasts (
    id              SERIAL PRIMARY KEY,
    catchment_id    INTEGER NOT NULL REFERENCES catchment_areas(id),
    forecast_date   DATE NOT NULL,
    precipitation_mm DOUBLE PRECISION NOT NULL,
    threshold_mm    DOUBLE PRECISION NOT NULL,
    is_warning      BOOLEAN NOT NULL,
    source          TEXT NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (catchment_id, forecast_date)
);
