# 2026 holdout labels

Written on 12 November 2026 from dated public reports only, before any model was scored on these labels.
Note: the deployed v2 model's 2026 scores had been seen once on the dashboard during the demonstration on
11 November; the labels below were taken from the reports and not adjusted to those scores.

## Rule
- **Flood**: a credible dated report (national news, Kenya Red Cross, National Police Service, ReliefWeb or
  Copernicus) describes flooding that day at a named place lying in one of the catchment's wards
  (`catchment_areas.wards`).
- **Unknown**: the two days either side of a flood day in the same catchment; days whose reports name only
  "Nairobi", "the city" or a general area; days with an official warning or evacuation but no reported flooding.
- **No flood**: every other day from 1 January to 30 September 2026.
- Flood days in one catchment less than three days apart form one event.

This is a weaker standard than the training labels (at least three Groundsource reports per event), so the
holdout may contain more small floods and some date uncertainty. Places outside all three catchments
(Ruai, Githurai, Kahawa West, Syokimau, Katani, the JKIA exit) are not used.

## Events and evidence

| Days | Catchments | Places named, by catchment | Sources |
|---|---|---|---|
| 17 Feb (evening) | none labelled flood; unknown for all three | Ruai only (outside the catchments); other reports say "parts of Nairobi" | The Star 18 Feb 2026; The Kenya Times 18 Feb 2026 |
| 5 Mar | Ngong, Nairobi River (flood); Mathare unknown | Kilimani, Nairobi West, South B, South C; Westlands (no ward match) | Copernicus GloFAS / FloodList, 27 Apr 2026 ("from 05 March") |
| 6 to 7 Mar (night of 6th) | all three | Ngong: Mukuru kwa Njenga, kwa Reuben, Viwandani, Kibra, South B, South C, Pipeline, Nairobi West. Nairobi River: CBD (Kenyatta Avenue, Kirinyaga Road), Grogan, Kariokor, Roysambu, Umoja, Baba Dogo, Kariobangi, Dandora. Mathare: Mathare, Huruma, Parklands | Kenya Red Cross and NPS via Kenyans.co.ke, People Daily, The Standard, Nation, The Star (6 to 9 Mar 2026) |
| 8 Mar | Mathare | Parklands Avenue flooded after the downpour | The Star, 9 Mar 2026 |
| 14 to 15 Mar (Saturday night) | all three | Ngong: Bunyala Road, Kibera, South B, Kilimani, Ngong Road (Ngando). Nairobi River: Moi Avenue, Kenyatta Avenue, Taifa Road, Kawangware, Kilimani. Mathare: Parklands, Lower Kabete | Kenya Red Cross via People Daily 15 Mar; Nation 15 Mar; The Star 15 Mar 2026 |
| 20 Mar | Ngong unknown | Evacuation ordered downstream of Nairobi Dam; no flooding reported | ReliefWeb ECHO Daily Flash, 23 Mar 2026 |
| 26 Mar | unknown for all three | One retrospective article names only "the city" | The Standard, 31 May 2026 |
| 27 to 28 Apr | Nairobi River 27 and 28; Ngong 28; Mathare unknown 28 | Season Road (27th); Utawala (Ngong), Njiru and Kariokor (Nairobi River) on 28th | Kenyans.co.ke 28 and 29 Apr 2026; Al Jazeera 3 May 2026 (general) |
| 29 Apr | unknown for all three | NPS warning for Kileleshwa, Ngara, Kibra, Kasarani and others | Kenyans.co.ke, 29 Apr 2026 |
| 30 Apr to 1 May (Thursday night) | all three | Ngong: Mukuru kwa Njenga, Lang'ata Road near T-Mall. Mathare and Nairobi River: Kinoo | NTV Kenya, 1 May 2026; People Daily 1 May; The Standard 2 May 2026 |

No dated Nairobi flood reports were found for January, from 16 May to 30 September, or for the heavy rain of
11 May 2026, so those days are labelled no flood.

## Caveat on inputs
The live feed takes IMERG from NASA's early release (about one day behind); the training data used the final
release. Mean IMERG rates are lower in 2026 (peak rate 0.79 against 1.22 mm/h for January to September 2025),
which may affect the scores. CHIRPS, ERA5-Land, soil moisture, temperature and pressure match the training scale.
