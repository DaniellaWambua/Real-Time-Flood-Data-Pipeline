# Source log

| Dataset | Source | Download date | Area covered | DOI | Notes | Saved file |
|---|---|---|---|---|---|---|
| NASADEM Global DEM, bare earth (DTM), 1 arc-second | https://portal.opentopography.org/raster?opentopoID=OTSDEM.032021.4326.2 | 2 November 2026 | Lower-left 36.55, -1.55 to upper-right 37.20, -1.00 | 10.5069/G93T9FD9 | Heights use the EGM1996 geoid. The portal page stated no licence, so check the NASA terms later. | 04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif |
| OpenStreetMap waterways named Nairobi, Mathare, Ngong or Motoine | Overpass API, https://overpass-api.de/api/interpreter | 2 November 2026 | South -1.55, west 36.55, north -1.00, east 37.20 | n/a | Name filter "Nairobi\|Mathare\|Ngong\|Motoine", case-insensitive. Licence ODbL, credit "OpenStreetMap contributors". Used as a reference for checking derived streams, not as a training input. | 05_spatial/raw/osm_waterways_nairobi.json |
