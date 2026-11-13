// The ten readings the model takes, with the label and unit shown. Keys are the columns
// GET /api/readings/recent returns. Rainfall-like totals are drawn as bars, the rest as lines.
export const READINGS = [
  { key: "rainfall_mm", label: "Rainfall, CHIRPS", unit: "mm", variant: "bars", group: "Rainfall" },
  { key: "era5_rain_mm", label: "Rainfall, ERA5-Land", unit: "mm", variant: "bars", group: "Rainfall" },
  { key: "imerg_total_mm", label: "IMERG daily total", unit: "mm", variant: "bars", group: "Rainfall" },
  { key: "imerg_max_rate", label: "IMERG peak rate", unit: "mm/h", variant: "line", group: "Rainfall" },
  { key: "imerg_hours_ge5", label: "Hours above 5 mm", unit: "h", variant: "bars", group: "Rainfall" },
  { key: "soil_1", label: "Soil water, 0 to 7 cm", unit: "m3/m3", variant: "line", group: "Soil water" },
  { key: "soil_2", label: "Soil water, 7 to 28 cm", unit: "m3/m3", variant: "line", group: "Soil water" },
  { key: "temp_c", label: "Temperature", unit: "°C", variant: "line", group: "Atmosphere" },
  { key: "dewpoint_depression", label: "Dewpoint depression", unit: "°C", variant: "line", group: "Atmosphere" },
  { key: "pressure_hpa", label: "Surface pressure", unit: "hPa", variant: "line", group: "Atmosphere" },
];

export const READING_GROUPS = ["Rainfall", "Soil water", "Atmosphere"];

// Charted by default: CHIRPS rainfall, the IMERG total and both soil layers.
export const DEFAULT_READINGS = ["rainfall_mm", "imerg_total_mm", "soil_1", "soil_2"];

export function readingLabel(key) {
  return READINGS.find((r) => r.key === key)?.label ?? key;
}

export function formatReading(value, key) {
  const reading = READINGS.find((r) => r.key === key);
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(2)} ${reading ? reading.unit : ""}`.trim();
}
