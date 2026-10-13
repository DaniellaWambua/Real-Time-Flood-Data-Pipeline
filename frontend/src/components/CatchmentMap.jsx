import { CircleMarker, MapContainer, TileLayer, Tooltip, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./CatchmentMap.css";

// Leaflet's CircleMarker takes a literal color prop, it cannot read CSS
// custom properties, so these stay literal hex matching theme.css
// rather than themed values. Default marker color is --accent (light
// mode); callers that need risk-based coloring (the main dashboard)
// pass their own colorFor() instead.
const DEFAULT_COLOR = "#2a78d6";
const SELECTED_RING = "#0b0b0b";

// A single catchment (the data stream monitor, after Daniella asked for
// the one selected river rather than the whole-country view) gets a
// close, fixed zoom centred on it instead of a bounds fit: fitBounds on
// a single point zooms Leaflet all the way to its max level, giving an
// oddly block-by-block view rather than the neighbourhood-level view a
// labelled river pin wants (see the Google Maps reference Daniella sent).
const FOCUSED_ZOOM = 14;

// Clicking empty map background (not a marker) clears the selection.
// react-leaflet has no prop for this, it has to be a map event listener,
// which only works as its own component inside <MapContainer>.
function ClearSelectionOnMapClick({ onClear }) {
  useMapEvents({ click: onClear });
  return null;
}

/**
 * A catchment-location map, shared by the main dashboard and the data
 * stream monitor so both screens show the same markers and the same
 * click-to-select behaviour instead of two separate implementations.
 *
 * `colorFor(catchment)` is optional and lets a caller encode something
 * per marker (the dashboard uses it for alert-severity risk colour);
 * without it every marker uses the one default accent colour.
 * `onSelect` is optional too, a map with nothing to select (none here
 * yet) just shows the catchments.
 *
 * Pass a single-item `catchments` array (the data stream monitor, for
 * its one selected river) to switch into the focused, labelled, fixed-
 * zoom mode described above; pass the full list (the main dashboard)
 * for the usual all-catchments bounds-fit view.
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

  // MapContainer only reads center/zoom/bounds on first mount; Leaflet
  // treats the map as stateful afterwards (it assumes the viewer may
  // have panned manually) and never recentres on a prop change alone.
  // In focused mode that silently broke switching rivers, the map just
  // kept showing wherever it first centred. Keying by the focused
  // catchment forces a fresh map instance, and therefore a fresh
  // initial view, each time the selection changes. The all-catchments
  // bounds view keeps one stable key, so it is unaffected, it never
  // needed to recentre after the first fit.
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
