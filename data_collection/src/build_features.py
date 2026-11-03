import pandas as pd
import numpy as np

D = "data_collection/data/"
ch = pd.read_csv(D + "02_weather/processed/chirps_daily_2004_2025.csv", parse_dates=["date"])
er = pd.read_csv(D + "02_weather/processed/era5land_daily_2004_2025.csv", parse_dates=["date"])
lab = pd.read_csv(D + "01_flood_labels/processed/daily_labelled_2015_2025.csv", parse_dates=["date"])

w = ch.merge(er, on=["catchment", "date"]).sort_values(["catchment", "date"])
w["rain_mm"] = w["precipitation"].clip(lower=0)
w["era5_rain_mm"] = w["total_precipitation_sum"].clip(lower=0) * 1000
w["temp_c"] = w["temperature_2m"] - 273.15
w["dewpoint_depression"] = w["temperature_2m"] - w["dewpoint_temperature_2m"]
w["pressure_hpa"] = w["surface_pressure"] / 100
w["soil_1"] = w["volumetric_soil_water_layer_1"]
w["soil_2"] = w["volumetric_soil_water_layer_2"]

g = w.groupby("catchment")
for n in (3, 7, 14, 30):
    w[f"rain_sum_{n}d"] = g["rain_mm"].transform(lambda s: s.rolling(n, min_periods=n).sum())
w["pressure_change_1d"] = g["pressure_hpa"].diff()

def api(s, k=0.9):
    out, prev = [], 0.0
    for v in s:
        prev = v + k * prev
        out.append(prev)
    return pd.Series(out, index=s.index)

def dry_run(s):
    out, c = [], 0
    for v in s:
        c = 0 if v >= 1 else c + 1
        out.append(c)
    return pd.Series(out, index=s.index)

w["api"] = w.groupby("catchment")["rain_mm"].transform(api)
w["days_since_rain"] = w.groupby("catchment")["rain_mm"].transform(dry_run)
w["month"] = w["date"].dt.month
w["month_sin"] = np.sin(2 * np.pi * w["month"] / 12)
w["month_cos"] = np.cos(2 * np.pi * w["month"] / 12)
base = (w[w["date"] < "2015-01-01"].groupby(["catchment", "month"])["rain_mm"]
        .mean().rename("clim_rain").reset_index())
w = w.merge(base, on=["catchment", "month"], how="left")
w["rain_anom_7d"] = w["rain_sum_7d"] - 7 * w["clim_rain"]

im = pd.concat([
    pd.read_csv(D + "02_weather/processed/imerg_daily_2015_2020.csv", parse_dates=["date"]),
    pd.read_csv(D + "02_weather/processed/imerg_daily_2021_2025.csv", parse_dates=["date"]),
])
w = w.merge(im, on=["catchment", "date"], how="left")

cols = ["catchment", "date", "rain_mm", "rain_sum_3d", "rain_sum_7d", "rain_sum_14d",
        "rain_sum_30d", "era5_rain_mm", "temp_c", "dewpoint_depression",
        "pressure_hpa", "pressure_change_1d", "soil_1", "soil_2",
        "api", "days_since_rain", "month_sin", "month_cos", "rain_anom_7d",
        "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5"]
df = w[cols].merge(lab[["catchment", "date", "label_status", "event_id"]],
                   on=["catchment", "date"], how="inner")
df = df.sort_values(["catchment", "date"])
df["next_status"] = df.groupby("catchment")["label_status"].shift(-1)

df.to_csv(D + "08_model_ready/features_daily.csv", index=False)
print(df.shape)
print(df.isna().sum()[df.isna().sum() > 0])
print(df.groupby("label_status")[["rain_mm", "rain_sum_3d", "rain_sum_7d", "soil_2", "imerg_max_rate", "imerg_hours_ge5"]].mean().round(2))