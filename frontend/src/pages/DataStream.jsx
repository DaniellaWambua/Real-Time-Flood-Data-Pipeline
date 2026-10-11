import { useEffect, useState } from "react";
import LineChart from "../components/LineChart";
import { get } from "../api";

// One feature per chart, deliberately: rainfall (mm) and river discharge
// (m3/s) are different scales, and the dataviz skill's "one axis" rule
// means they never share a y-axis. Soil moisture, evaporation and ONI
// come from hydro_data_records too (db/init/02_schema.sql) but need the
// backend to have been fed through Kafka with the ERA5 fields populated
// to be worth plotting; rainfall and discharge are what the Kafka test
// run actually produced.
const FEATURES = [
  { key: "rainfall_mm", label: "Rainfall", unit: "mm" },
  { key: "river_discharge_m3s", label: "River discharge", unit: "m3/s" },
  { key: "soil_moisture_m3m3", label: "Soil moisture", unit: "m3/m3" },
  { key: "evaporation_mm", label: "Evaporation", unit: "mm" },
];

export default function DataStream() {
  const [catchments, setCatchments] = useState([]);
  const [catchment, setCatchment] = useState("");
  const [featureKey, setFeatureKey] = useState(FEATURES[0].key);
  const [readings, setReadings] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/catchments").then((rows) => {
      setCatchments(rows);
      if (rows.length > 0) setCatchment(rows[0].name);
    });
  }, []);

  useEffect(() => {
    if (!catchment) return;
    get("/api/readings/recent", { catchment, limit: 200 })
      .then((rows) => {
        setReadings(rows);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [catchment]);

  const feature = FEATURES.find((f) => f.key === featureKey);

  // The API returns newest first; the chart reads left-to-right in time.
  const points = (readings ?? [])
    .filter((row) => row[featureKey] !== null)
    .map((row) => ({ x: new Date(row.recorded_at), y: row[featureKey] }))
    .reverse();

  return (
    <section>
      <h1>Data stream monitor</h1>

      <div className="filter-row">
        <label>
          Catchment
          <select value={catchment} onChange={(e) => setCatchment(e.target.value)}>
            {catchments.map((c) => (
              <option key={c.id} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Feature
          <select value={featureKey} onChange={(e) => setFeatureKey(e.target.value)}>
            {FEATURES.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}

      {readings && (
        <LineChart
          title={`${feature.label} at ${catchment}, most recent ${points.length} readings`}
          unit={feature.unit}
          points={points}
        />
      )}
    </section>
  );
}
