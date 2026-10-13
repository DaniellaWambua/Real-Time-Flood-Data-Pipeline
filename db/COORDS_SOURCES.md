# Catchment coordinate sources

`db/seed.py`'s `CATCHMENT_COORDS` used to be rough, hand-picked single-point
estimates (see that file's git history). On 2026-10-11 they were replaced
with points taken directly from OpenStreetMap's own river geometry, after
Daniella noticed the dashboard's map markers (and the labels the data
stream monitor now shows on them) were landing noticeably off the actual
river, on nearby, unrelated features in a couple of cases.

## Method

For each river, two lookups against the public OpenStreetMap APIs:

1. **Locality centre** — `https://nominatim.openstreetmap.org/search?q=<locality>, Kenya&format=jsonv2`
   for the specific place each catchment is already associated with via
   `CATCHMENT_COUNTY` (Nairobi CBD, Huruma, Kibera, Ongata Rongai/Karen,
   Ahero, Garissa), to get a reference point to measure against.
2. **River geometry near that locality** — the Overpass API
   (`https://overpass-api.de/api/interpreter`), querying for the
   `waterway` way tagged with that river's name within a bounding box
   around the locality centre, e.g.:

   ```
   [out:json][timeout:20];
   way["waterway"]["name"="Mathare River"](-1.2787,36.8515,-1.2387,36.8915);
   out geom;
   ```

   Every node of every matching way was then compared to the locality
   centre, and the single nearest node's coordinates were taken as the
   catchment's point, so it sits exactly on OSM's mapped river channel,
   as close as that channel comes to the named locality.

## Results

| Catchment | OSM waterway name matched | Distance from locality centre |
|---|---|---|
| Nairobi River | `Nairobi River` | 0.84 km from Nairobi CBD |
| Mathare | `Mathare River` | 0.39 km from Huruma |
| Ngong | `Ngong river` | 0.10 km from Kibera |
| Motoine | `Motoine River` | 8.48 km from Ongata Rongai town (see caveat below) |
| Nyando River | `Nyando river` | 0.21 km from Ahero |
| Tana River | `Tana River` | 0.79 km from central Garissa |

## Known caveat: Motoine

OSM's mapped extent of the Motoine River currently stops in Karen; it is
not mapped any further south, into Ongata Rongai itself, where Motoine
River flooding is the thing usually reported in the news. There was no
mapped segment there to pick a point from. Daniella chose to use the
southmost point OSM actually has mapped (in Karen) rather than keep an
unverified Ongata Rongai town-centre guess (2026-10-11 conversation).
If the real ERA5/CHIRPS extraction notebook coordinates turn up (see
project-checklist.md), or OSM's mapping of this river is extended south,
this is the one entry most worth revisiting.

## Still not the final answer

These are a solid, verifiable improvement over the original guesses, but
they are still not the coordinates used in the ERA5/CHIRPS extraction
notebooks that this project's actual historical dataset came from, which
live outside this repository. Those remain the authoritative source if
they turn up.
