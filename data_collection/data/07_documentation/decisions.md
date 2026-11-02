# Decisions

## D1, 2 November 2026, catchment design
Three exclusive sub-catchments. Mathare, Ngong (the full area above the Ngong outlet, which includes Motoine) and the Nairobi River (excluding Mathare and Ngong). Each outlet is delineated and the upstream areas are subtracted so the areas do not overlap. Reason, flood labels are attached to one area each, and nested catchments would count an upstream flood in every downstream area. Motoine was merged into Ngong because it had no flood episode with three or more independent reports, so it could not be evaluated alone.

## D2, 2 November 2026, scope and period
Nairobi only. Tana, Nzoia and Nyando are not part of this rebuild. Weather and static data are collected for 2004 to 2025. Flood labels are used from 2015 to 2025, because news-derived evidence is sparse before 2015 and an absence of reports then does not mean an absence of floods. Earlier EM-DAT events stay in the register as county-level context.

## D3, 2 November 2026, outlet placement
Outlets were placed using the upstream-area profile along each mapped river (profile_rivers.py), which shows where each tributary joins its main river. Mathare is placed at longitude 36.880 and Ngong at 36.941, 1 to 2 km above their junctions. The Nairobi River outlet is 500 m downstream of the Ngong junction. Every outlet is snapped to the highest flow accumulation within 3 cells, about 90 m. Reason, at a junction the main river has the largest accumulation, so an outlet too close to it captures the whole main river catchment.

## D4 Labelling and splits
Days are labelled flood, unknown or no_flood. Unknown days are excluded from training and testing negatives. Splits must keep every event_id inside one fold, and evaluation is walk-forward by year so that no future data informs earlier predictions. Labels cover 2015 to 2025 only because Groundsource is sparse before 2015.
