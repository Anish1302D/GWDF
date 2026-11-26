import React, { useEffect, useMemo, useRef } from "react";
import L from "leaflet";

const FILL_COLORS = {
  Safe: "#16A34A",
  Watch: "#D97706",
  Critical: "#DC2626",
  "Insufficient Data": "#9CA3AF",
};

export default function MapView({
  geoJson,
  blocks,
  selectedBlockId,
  onSelectBlock,
  t,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const geoLayerRef = useRef(null);

  const blockLookup = useMemo(() => {
    const map = new Map();
    for (const b of blocks) {
      map.set(b.block_id, b);
    }
    return map;
  }, [blocks]);

  // Initialize Leaflet map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [19.15, 76.15],
      zoom: 6,
      minZoom: 5,
      maxZoom: 11,
      scrollWheelZoom: true,
    });

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; CARTO',
      subdomains: "abcd",
      maxZoom: 18,
    }).addTo(map);

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Render or update GeoJSON layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geoJson) return;

    if (geoLayerRef.current) {
      geoLayerRef.current.remove();
      geoLayerRef.current = null;
    }

    const layer = L.geoJSON(geoJson, {
      style: (feature) => {
        const bid = feature?.properties?.block_id;
        const info = blockLookup.get(bid);
        const rc = info?.risk_class || "Insufficient Data";
        const isSelected = bid === selectedBlockId;
        return {
          fillColor: FILL_COLORS[rc] || FILL_COLORS["Insufficient Data"],
          fillOpacity: isSelected ? 0.85 : 0.65,
          color: isSelected ? "#0F172A" : "#FFFFFF",
          weight: isSelected ? 2.6 : 0.7,
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

    // Highlight selected polygon on top
    layer.eachLayer((subLayer) => {
      if (subLayer?.feature?.properties?.block_id === selectedBlockId) {
        subLayer.bringToFront();
      }
    });
  }, [geoJson, blockLookup, selectedBlockId, onSelectBlock, t]);

  return (
    <div className="map-card card">
      <div ref={containerRef} className="leaflet-map-container" aria-label="Maharashtra block groundwater risk map" />
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
