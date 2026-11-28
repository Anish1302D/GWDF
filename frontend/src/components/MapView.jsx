import React, { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { ArrowLeft } from "lucide-react";

const FILL_COLORS = {
  Safe: "#16A34A",
  Watch: "#D97706",
  Critical: "#DC2626",
  "Insufficient Data": "#9CA3AF",
};

export default function MapView({
  mode, // "india" | "state"
  indiaStatesGeoJson,
  statesSummary,
  stateBlocksGeoJson,
  blocks,
  selectedStateCode,
  selectedBlockId,
  onSelectState,
  onSelectBlock,
  t,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const geoLayerRef = useRef(null);
  const prevStateRef = useRef(null);

  const stateLookup = useMemo(() => {
    const m = new Map();
    for (const s of statesSummary || []) {
      m.set(s.state_code, s);
    }
    return m;
  }, [statesSummary]);

  const blockLookup = useMemo(() => {
    const map = new Map();
      for (const b of blocks || []) {
        map.set(b.block_id, b);
      }
      return map;
    }, [blocks]);

  // Initialize Leaflet map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [22.3, 79.2],
      zoom: 5,
      minZoom: 4,
      maxZoom: 12,
      scrollWheelZoom: true,
    });

    const maptilerKey = (import.meta.env.VITE_MAPTILER_KEY || "").trim();
    const mtAttr =
      '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

    const lightCanvas = maptilerKey
      ? L.tileLayer(
        `https://api.maptiler.com/maps/dataviz-light/256/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(maptilerKey)}`,
          { attribution: mtAttr, maxZoom: 19 }
        )
      : L.layerGroup([
          L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            { attribution: "Tiles &copy; Esri", maxZoom: 16 }
          ),
          L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
            { maxZoom: 16 }
          ),
        ]);

  const osmStreets = maptilerKey
    ? L.tileLayer(
      `https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(maptilerKey)}`,
    { attribution: mtAttr, maxZoom: 19 }
        )
      : L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
        });

const terrainTopo = maptilerKey
  ? L.tileLayer(
    `https://api.maptiler.com/maps/topo-v2/256/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(maptilerKey)}`,
  { attribution: mtAttr, maxZoom: 18 }
        )
      : L.tileLayer(
"https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Tiles &copy; Esri", maxZoom: 18 }
        );

lightCanvas.addTo(map);
L.control
  .layers(
    {
      "Light Canvas": lightCanvas,
      "Towns & Roads": osmStreets,
      "Topographic / Terrain": terrainTopo,
    },
    null,
    { position: "topright" }
  )
  .addTo(map);

mapRef.current = map;
return () => {
  map.remove();
  mapRef.current = null;
};
  }, []);

// Render All-India States layer OR State Blocks layer
useEffect(() => {
  const map = mapRef.current;
  if (!map) return;

  if (geoLayerRef.current) {
    geoLayerRef.current.remove();
    geoLayerRef.current = null;
  }

    if(mode === "india") {
      if (!indiaStatesGeoJson) return;
  const layer = L.geoJSON(indiaStatesGeoJson, {
    style: (feature) => {
      const sc = feature?.properties?.state_code;
      const info = stateLookup.get(sc);
      const rc = info?.risk_class || "Insufficient Data";
      return {
        fillColor: FILL_COLORS[rc] || FILL_COLORS["Insufficient Data"],
        fillOpacity: 0.68,
        color: "#FFFFFF",
        weight: 1.2,
      };
    },
    onEachFeature: (feature, featLayer) => {
      const sc = feature?.properties?.state_code;
      const sName = feature?.properties?.state || sc;
      const info = stateLookup.get(sc);
      const rc = info?.risk_class || "Insufficient Data";
      const critTxt = info ? `Critical: ${info.critical} · Watch: ${info.watch}` : "No data";
      const meanTxt =
        info?.mean_predicted_depth_mbgl != null
          ? `Mean Forecast: ${info.mean_predicted_depth_mbgl.toFixed(1)} m bgl`
          : "";
      featLayer.bindTooltip(
        `<strong>${sName}</strong> (${sc})<br/>${rc} · ${critTxt}<br/>${meanTxt}<br/><em>Click to explore blocks →</em>`,
        { sticky: true, direction: "top" }
      );
      featLayer.on("click", () => {
        onSelectState(sc);
      });
    },
  }).addTo(map);

  geoLayerRef.current = layer;
  if (prevStateRef.current !== "ALL") {
    map.setView([22.5, 79.5], 5);
    prevStateRef.current = "ALL";
  }
  return;
}

    if (!stateBlocksGeoJson) return;
const layer = L.geoJSON(stateBlocksGeoJson, {
  style: (feature) => {
    const bid = feature?.properties?.block_id;
    const info = blockLookup.get(bid);
    const rc = info?.risk_class || "Insufficient Data";
    const isSelected = bid === selectedBlockId;
    return {
      fillColor: FILL_COLORS[rc] || FILL_COLORS["Insufficient Data"],
      fillOpacity: isSelected ? 0.86 : 0.66,
      color: isSelected ? "#0F172A" : "#FFFFFF",
      weight: isSelected ? 2.5 : 0.65,
    };
  },
  onEachFeature: (feature, featLayer) => {
    const bid = feature?.properties?.block_id;
    const info = blockLookup.get(bid);
    const bName = feature?.properties?.block_name || bid;
    const dName = feature?.properties?.district || "";
    const rc = info?.risk_class || "Insufficient Data";
    const predTxt =
      info?.predicted_depth_mbgl != null
        ? `${info.predicted_depth_mbgl.toFixed(1)} m bgl`
        : "N/A";
    const riskLabel = t.riskClasses[rc] || rc;

    featLayer.bindTooltip(
      `<strong>${bName}</strong> (${dName})<br/>${riskLabel} · ${predTxt}`,
      { sticky: true, direction: "top" }
    );
    featLayer.on("click", () => {
      onSelectBlock(bid);
    });
  },
}).addTo(map);

geoLayerRef.current = layer;

if (prevStateRef.current !== selectedStateCode) {
  const bounds = layer.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [16, 16], maxZoom: 9 });
  }
  prevStateRef.current = selectedStateCode;
}

layer.eachLayer((subLayer) => {
  if (subLayer?.feature?.properties?.block_id === selectedBlockId) {
    subLayer.bringToFront();
  }
});
  }, [
  mode,
  indiaStatesGeoJson,
  statesSummary,
  stateLookup,
  stateBlocksGeoJson,
  blockLookup,
  selectedStateCode,
  selectedBlockId,
  onSelectState,
  onSelectBlock,
  t,
]);

return (
  <div className="map-card card">
    <div className="map-Floating-bar">
      {mode === "state" ? (
        <button
          type="button"
          className="map-back-pill"
          onClick={() => onSelectState("ALL")}
        >
          <ArrowLeft size={14} />
          <span>All-India Map</span>
        </button>
      ) : (
        <span className="map-hint-pill">
          🇮🇳 Click any Indian State to drill into Block / Tehsil forecasts
        </span>
      )}
    </div>

    <div
      ref={containerRef}
      className="leaflet-map-container"
      aria-label="India groundwater risk map"
    />

    <div className="map-legend" role="region" aria-label="Risk legend">
      {["Critical", "Watch", "Safe", "Insufficient Data"].map((rc) => (
        <div key={rc} className="legend-item">
          <span
            className="legend-swatch"
            style={{ backgroundColor: FILL_COLORS[rc] }}
            aria-hidden="true"
          />
          <span>{t.riskClasses[rc] || rc}</span>
        </div>
      ))}
    </div>
  </div>
);
}
