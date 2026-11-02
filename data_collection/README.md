# Data collection

Rebuild of the flood dataset for the Nairobi catchments, 2004 to 2025. Every source is downloaded and recorded by hand, with its origin and download date.

## Layout

- 01_flood_labels holds flood event sources and the event register
- 02_weather holds rainfall and reanalysis weather data
- 03_hydrology holds river discharge and gauge data
- 04_environmental holds static layers such as elevation, land cover and built-up area
- 05_spatial holds catchment boundaries and administrative geometry
- 06_operational holds the forecast archive and near-real-time feeds
- 07_documentation holds the manifest, source notes and audit records

## Rules

- raw is never edited by hand
- processed can always be regenerated from raw using the code in src
- Large raw files are not committed, so every download is logged in 07_documentation
