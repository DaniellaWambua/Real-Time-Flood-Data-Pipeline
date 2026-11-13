import { CircleMarker, MapContainer, TileLayer, Tooltip, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./CatchmentMap.css";

// Leaflet cannot read CSS variables, so marker colours are literal hex matching theme.css.
const DEFAULT_COLOR = "#2a78d6";
const SELECTED_RING = "#0b0b0b";

// One catchment gets a fixed neighbourhood zoom; fitBounds on a single point zooms in too far.
const FOCUSED_ZOOM = 14;

// Clicking empty map background clears the selection (needs its own component inside MapContainer).
function ClearSelectionOnMapClick({ onClear }) {
  useMapEvents({ click: onClear });
  return null;
}

/**
 * Catchment map shared by the dashboard and the data stream monitor.
 * colorFor(catchment) sets each marker's colour; onSelect is optional.
 * A single catchment switches to the focused, labelled view.
 */
export default function CatchmentMap({
  catchments,
  selectedName,
  onSelect,
  colorFor,
  mapClassName = "",
}) {
  if (catchments.length === 0) return null;

  const focused = catchments.length === 1;
  const containerProps = focused
    ? { center: [catchments[0].latitude, catchments[0].longitude], zoom: FOCUSED_ZOOM }
    : { bounds: catchments.map((c) => [c.latitude, c.longitude]) };

  // MapContainer only reads its view on mount, so keying by the focused catchment recentres it.
  const mapKey = focused ? `focused-${catchments[0].id}` : "all";

  return (
    <div className="catchment-map-card">
      <MapContainer
        key={mapKey}
        {...containerProps}
        className={`catchment-map ${mapClassName}`.trim()}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {onSelect && <ClearSelectionOnMapClick onClear={() => onSelect(null)} />}
        {catchments.map((catchment) => {
          const isSelected = catchment.name === selectedName;
          const fillColor = colorFor ? colorFor(catchment) : DEFAULT_COLOR;
          return (
            <CircleMarker
              key={catchment.id}
              center={[catchment.latitude, catchment.longitude]}
              radius={isSelected ? 14 : 10}
              pathOptions={{
                color: isSelected ? SELECTED_RING : fillColor,
                weight: isSelected ? 2 : 1,
                fillColor,
                fillOpacity: 0.85,
              }}
              eventHandlers={
                onSelect
                  ? {
                      click: (event) => {
                        event.originalEvent.stopPropagation();
                        onSelect(catchment.name);
                      },
                    }
                  : undefined
              }
            >
              {focused && (
                <Tooltip permanent direction="right" offset={[10, 0]} className="catchment-map-label">
                  {catchment.name}
                </Tooltip>
              )}
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
