# Real-Time Flood Data Pipeline for Early Warning Systems Using LSTM

A flood early warning system for three river catchments in Nairobi: the Nairobi River, Mathare and Ngong.
Final-year capstone project, BSc Informatics and Computer Science, Strathmore University.
Supervisor: Dr Dickson Owuor.

Live system: https://nairobifloodews.live (accounts are created by an administrator).

## How it works

1. **Ingestion.** Each day a producer fetches satellite rainfall (CHIRPS, GPM IMERG) and ERA5-Land soil
   water, temperature and pressure for each catchment from Google Earth Engine, and publishes one reading
   per catchment on a Kafka topic. A second producer publishes Open-Meteo's three-day rainfall forecast.
2. **Stream processing.** A consumer validates each reading, rejects duplicates, stores it in PostgreSQL
   (TimescaleDB and PostGIS) and sends it for scoring.
3. **Detection.** An LSTM reads the last 14 days for the catchment and gives a flood score. Eight models
   trained with different seeds are averaged. A score at or above the threshold raises an alert, and
   consecutive flagged days form one incident. Days that CHIRPS has not yet published are scored early by
   a second model trained without it, and confirmed or withdrawn once CHIRPS arrives.
4. **Response.** A Disaster Management officer verifies or dismisses each incident before Emergency
   Responders and Government Officials are notified. Responders record what they found, which feeds
   back as labels for retraining.

On the 2024 to 2025 test years the model detected 20 of the 38 recorded flood events, with about one false
alarm episode per catchment per year.

## Repository layout

```
backend/          Flask API: authentication, dashboard, incidents, notifications and flood detection
ingestion/        Kafka producer (live, forecast and replay modes) and stream-processing consumer
frontend/         React dashboard (Vite), installable as an app with push notifications
db/               Docker Compose for PostgreSQL and Kafka, schema, seed and migration scripts
models/           Saved LSTM weights, configuration and evaluation (flood_lstm is the deployed model)
data_collection/  Data download, labelling, training and evaluation scripts, and their outputs
colab/            Notebooks used for training on Google Colab
deploy/           Production deployment (Docker Compose, Caddy, backups, schedule)
tests/            Automated tests (pytest)
reports/figures/  Figures used in the report
archive/          Code from the earlier autoencoder design, kept for reference
```

## Running it locally

Requirements: Docker, Python 3.9 or later and Node.js.

1. Copy `backend/.env.example` to `backend/.env`, fill in the values, and install the backend's packages
   (`pip install -r backend/requirements.txt`).
2. Start PostgreSQL and Kafka, then seed the database (from `db/`):
   ```bash
   docker compose --env-file ../backend/.env up -d
   python seed.py
   python migrate_final_catchments.py
   python add_catchment_wards.py
   ```
3. Create the first account and start the API (from `backend/`):
   ```bash
   python create_user.py admin <password> system_administrator
   python app.py
   ```
4. Start the stream processor, then replay the historical readings (from `ingestion/`, in two terminals):
   ```bash
   pip install -r requirements.txt
   python consumer.py
   python producer.py --interval 0.1
   ```
5. Start the dashboard (from `frontend/`) and open http://localhost:5173:
   ```bash
   npm install
   npm run dev
   ```

The live feed (`producer.py --live`) also needs Earth Engine credentials.

## Tests

```bash
pip install pytest
python -m pytest tests
```

## Data sources and licences

This repository contains data derived from the sources below, each used under the terms shown.

| Data | Used for | Source | Licence and credit |
|---|---|---|---|
| CHIRPS daily rainfall | Model input | Funk et al. (2015), via Google Earth Engine `UCSB-CHG/CHIRPS/DAILY`, doi:10.15780/G6WG6X | Free to use; cite Funk et al. (2015) |
| GPM IMERG V07 | Model input | NASA, via Google Earth Engine | NASA open data; cite Huffman et al., doi:10.5067/GPM/IMERG/3B-HH/07 |
| ERA5-Land daily aggregates | Model input | Copernicus Climate Change Service, via Google Earth Engine, doi:10.24381/cds.e2161bac | Contains modified Copernicus Climate Change Service information (2026) |
| Open-Meteo forecasts and forecast archive | Rainfall warning and forecast test | open-meteo.com | CC BY 4.0, "Weather data by Open-Meteo.com" |
| Groundsource flood events | Training labels | Cohen (2026), Google Research, doi:10.5281/zenodo.18647054 | CC BY 4.0 |
| NASADEM elevation | Catchment boundaries | NASA, via OpenTopography, doi:10.5069/G93T9FD9 | NASA open data |
| OpenStreetMap waterways and map tiles | Checking derived streams; dashboard map | © OpenStreetMap contributors | ODbL |
| Ward boundaries | Naming the places in each catchment | geoBoundaries, geoboundaries.org | CC BY 4.0 |
| Lato typeface | Dashboard | @fontsource/lato | SIL Open Font License 1.1 (`frontend/src/assets/fonts/OFL-LICENSE.txt`) |
| Font Awesome Free icons | Dashboard | fontawesome.com | CC BY 4.0 (`frontend/src/assets/icons/FONT-AWESOME-LICENSE.txt`) |

**Not included.** EM-DAT (CRED, UCLouvain) and DesInventar were used to cross-check flood events during
labelling, but their terms do not allow their records to be shared, so they are not in this repository.
`event_register.csv` keeps only the EM-DAT record numbers, so each event can be traced on emdat.be.
Rerunning `build_register.py`, `crosscheck.py` or `match_places.py` needs your own download from those
databases; their results are already in the repository.

The 2026 holdout labels were written from dated public reports, listed in
`data_collection/data/01_flood_labels/holdout_2026/LABELS_2026.md`.
