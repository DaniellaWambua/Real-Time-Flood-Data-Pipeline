# Decisions

## D1, 2 November 2026, catchment design
Exclusive sub-catchments. Motoine, Ngong, Mathare and Nairobi River are four non-overlapping areas, built by delineating each outlet and subtracting the upstream areas. Reason, flood labels are attached to one area each, and nested catchments would count an upstream flood in every downstream area and give strongly correlated features. Rejected option, nested catchments.

## D2, 2 November 2026, scope
Nairobi only. Tana, Nzoia and Nyando are not part of this rebuild. Study window 2004 to 2025, to be revisited once the event register shows how many verifiable events exist before 2010.

## D3, 2 November 2026, outlet placement
Outlets were placed using the upstream-area profile along each mapped river (profile_rivers.py), which shows where each tributary joins its main river. Mathare is placed at longitude 36.880 and Ngong at 36.941, 1 to 2 km above their junctions. Motoine and the Nairobi River outlet, 500 m downstream of the Ngong junction, were confirmed by the profile. Every outlet is then snapped to the highest flow accumulation within 3 cells, about 90 m. Reason, at a junction the main river has the largest accumulation, so an outlet too close to it captures the whole main river catchment.
