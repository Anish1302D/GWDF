import React, { useMemo, useState } from "react";
import { Wheat, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

const CROPS = [
  { id: "bajra", name: "Bajra (Pearl Millet)", season: "Kharif", waterMm: 300, dripSavePct: 30 },
  { id: "chana", name: "Chana (Chickpea / Gram)", season: "Rabi", waterMm: 320, dripSavePct: 35 },
  { id: "mustard", name: "Mustard (Sarson)", season: "Rabi", waterMm: 340, dripSavePct: 30 },
  { id: "jowar", name: "Jowar (Sorghum)", season: "Kharif/Rabi", waterMm: 360, dripSavePct: 30 },
  { id: "tur", name: "Tur / Arhar (Pigeonpea)", season: "Kharif", waterMm: 480, dripSavePct: 40 },
  { id: "wheat", name: "Wheat", season: "Rabi", waterMm: 480, dripSavePct: 35 },
  { id: "groundnut", name: "Groundnut", season: "Kharif/Summer", waterMm: 510, dripSavePct: 40 },
  { id: "soybean", name: "Soybean", season: "Kharif", waterMm: 530, dripSavePct: 35 },
  { id: "maize", name: "Maize", season: "Kharif/Rabi", waterMm: 560, dripSavePct: 40 },
  { id: "cotton", name: "Cotton", season: "Kharif", waterMm: 740, dripSavePct: 48 },
  { id: "paddy", name: "Paddy (Rice)", season: "Kharif/Rabi", waterMm: 1200, dripSavePct: 35 },
  { id: "sugarcane", name: "Sugarcane", season: "Annual", waterMm: 1850, dripSavePct: 50 },
];

export default function CropAdvisor({ forecast }) {
  const [onlyRecommended, setOnlyRecommended] = useState(false);

  const evaluated = useMemo(() => {
    if (!forecast || forecast.risk_class === "Insufficient Data") return [];
    const rc = forecast.risk_class;
    const upper = forecast.upper_bound ?? forecast.predicted_depth_mbgl ?? 10;
    const rainPct = (forecast.rainfall_pct_of_normal || 100) / 100.0;
    const effectiveMonsoonMm = (forecast.normal_monsoon_mm || 750) * rainPct;

    return CROPS.map((c) => {
      let status = "recommended"; // "recommended" | "drip" | "avoid"
      let note = `Fits seasonal water budget (~${c.waterMm} mm).`;

      if (rc === "Critical" || upper >= 20) {
        if (c.waterMm >= 700) {
          status = "avoid";
          note = `High aquifer depletion risk (${upper.toFixed(1)} m P90) — avoid water-intensive ${c.name}.`;
        } else if (c.waterMm >= 460) {
          status = "drip";
          note = `Cultivate only with drip/sprinkler (~${c.dripSavePct}% water saved).`;
        } else {
          status = "recommended";
          note = `Low-water drought-hardy crop (~${c.waterMm} mm) well suited for stressed blocks.`;
        }
      } else if (rc === "Watch" || effectiveMonsoonMm < 580) {
        if (c.waterMm >= 1150) {
          status = "avoid";
          note = `Exceeds safe recharge budget (${Math.round(effectiveMonsoonMm)} mm scenario rain).`;
        } else if (c.waterMm >= 520) {
          status = "drip";
          note = `Use micro-irrigation (${c.dripSavePct}% water saving) to protect water table.`;
        }
      } else {
        if (c.waterMm >= 1500 && effectiveMonsoonMm < 950) {
          status = "drip";
          note = `Pair with subsurface/drip irrigation (${c.dripSavePct}% saving) to prevent drawdown.`;
        }
      }

      return { ...c, status, note };
    });
  }, [forecast]);

  if (!evaluated.length) return null;

  const visible = onlyRecommended
    ? evaluated.filter((c) => c.status !== "avoid")
    : evaluated;

  return (
    <div className="card crop-advisor-card">
      <div className="section-head-split">
        <div className="scenario-title-row">
          <Wheat size={19} className="accent-icon" aria-hidden="true" />
          <div>
            <h3>Smart Crop Water-Budget &amp; Sowing Matrix</h3>
            <p className="muted-text">
              Matched to predicted depth ({forecast.predicted_depth_mbgl?.toFixed(1)} m) &amp;{" "}
              {Math.round(((forecast.normal_monsoon_mm || 750) * (forecast.rainfall_pct_of_normal || 100)) / 100)}{" "}
              mm scenario monsoon rain
            </p>
          </div>
        </div>
        <label className="inline-toggle">
          <input
            type="checkbox"
            checked={onlyRecommended}
            onChange={(e) => setOnlyRecommended(e.target.checked)}
          />
          <span>Hide high-risk crops</span>
        </label>
      </div>

      <div className="crop-grid">
        {visible.map((c) => (
          <div key={c.id} className={`crop-tile crop-${c.status}`}>
            <div className="crop-tile-top">
              <strong>{c.name}</strong>
              {c.status === "recommended" && (
                <span className="crop-pill pill-ok">
                  <CheckCircle2 size={13} /> Recommended
                </span>
              )}
              {c.status === "drip" && (
                <span className="crop-pill pill-warn">
                  <AlertTriangle size={13} /> Drip Only
                </span>
              )}
              {c.status === "avoid" && (
                <span className="crop-pill pill-bad">
                  <XCircle size={13} /> Avoid
                </span>
              )}
            </div>
            <div className="crop-meta">
              {c.season} · Water need: <strong>{c.waterMm} mm</strong>
            </div>
            <p className="crop-note">{c.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
