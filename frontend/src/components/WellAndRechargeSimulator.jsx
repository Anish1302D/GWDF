import React, { useMemo, useState } from "react";
import { Gauge, CloudRainWind } from "lucide-react";

const STRUCTURES = [
  { id: "farm_pond", label: "Farm Pond / Khet Talab (35% capture)", coeff: 0.35 },
  { id: "check_dam", label: "Percolation Tank / Check-Dam (45% capture)", coeff: 0.45 },
  { id: "recharge_pit", label: "Borewell Recharge Shaft / Pit (55% capture)", coeff: 0.55 },
  { id: "rooftop", label: "Rooftop Rainwater Harvesting (80% capture)", coeff: 0.8 },
];

export default function WellAndRechargeSimulator({ forecast }) {
  const [subTab, setSubTab] = useState("well"); // "well" | "recharge"
  const [wellDepthInput, setWellDepthInput] = useState(50);
  const [wellUnit, setWellUnit] = useState("ft"); // "ft" | "m"

  const [areaInput, setAreaInput] = useState(2.0);
  const [areaUnit, setAreaUnit] = useState("acres"); // "acres" | "sqm"
  const [structureId, setStructureId] = useState("farm_pond");

  const wellEval = useMemo(() => {
    if (!forecast || forecast.predicted_depth_mbgl == null) return null;
    const wellMeters =
      wellUnit === "ft" ? Number(wellDepthInput || 0) * 0.3048 : Number(wellDepthInput || 0);
    const p50 = forecast.predicted_depth_mbgl;
    const p90 = forecast.upper_bound ?? p50 + 1.5;
    const bufferP50 = wellMeters - p50;
    const bufferP90 = wellMeters - p90;

    let severity = "safe";
    let headline = "Healthy Water Column Buffer";
    let detail = `Your well (${wellMeters.toFixed(1)} m) reaches ${bufferP90.toFixed(1)} m deeper than even the P90 dry-risk bound (${p90.toFixed(1)} m).`;

    if (bufferP50 <= 0.5) {
      severity = "critical";
      headline = "High Dry-Out Risk Next Season!";
      detail = `Predicted water table (${p50.toFixed(1)} m) is at or deeper than your well bottom (${wellMeters.toFixed(1)} m). Prioritize recharge and avoid summer pumping.`;
    } else if (bufferP90 <= 1.0) {
      severity = "watch";
      headline = "Thin Safety Margin Under Dry Scenario";
      detail = `Safe at median forecast (${p50.toFixed(1)} m), but worst-case P90 (${p90.toFixed(1)} m) comes within ${Math.max(0, bufferP90).toFixed(1)} m of your pump intake.`;
    }
    return { wellMeters, bufferP50, bufferP90, severity, headline, detail };
  }, [forecast, wellDepthInput, wellUnit]);

  const rechargeEval = useMemo(() => {
    if (!forecast) return null;
    const struct = STRUCTURES.find((s) => s.id === structureId) || STRUCTURES[0];
    const areaSqm =
      areaUnit === "acres" ? Number(areaInput || 0) * 4046.86 : Number(areaInput || 0);
    const rainMm =
      ((forecast.normal_monsoon_mm || 750) * (forecast.rainfall_pct_of_normal || 100)) / 100.0;
    // 1 mm of rain on 1 sq.m = 1 Litre
    const capturedLitres = Math.max(0, areaSqm * rainMm * struct.coeff);
    const cubicMeters = capturedLitres / 1000.0;
    const tankers10k = Math.round(capturedLitres / 10000.0);
    // 1 protective micro-irrigation of 35 mm across 1 acre (~141,640 L)
    const protectiveIrrigationsAcres = capturedLitres / 141640.0;
    return { rainMm, capturedLitres, cubicMeters, tankers10k, protectiveIrrigationsAcres };
  }, [forecast, areaInput, areaUnit, structureId]);

  if (!forecast || forecast.risk_class === "Insufficient Data") return null;

  return (
    <div className="card simulator-card">
      <div className="sim-tabs">
        <button
          type="button"
          className={`sim-tab-btn ${subTab === "well" ? "active" : ""}`}
          onClick={() => setSubTab("well")}
        >
          <Gauge size={15} />
          <span>My Borewell / Well Dry-Out Check</span>
        </button>
        <button
          type="button"
          className={`sim-tab-btn ${subTab === "recharge" ? "active" : ""}`}
          onClick={() => setSubTab("recharge")}
        >
          <CloudRainWind size={15} />
          <span>Rainwater Recharge Calculator</span>
        </button>
      </div>

      {subTab === "well" && wellEval && (
        <div className="sim-body">
          <div className="sim-inputs-row">
            <div className="selector-field">
              <label htmlFor="well-depth-input">Your Dug-Well / Borewell Depth</label>
              <input
                id="well-depth-input"
                type="number"
                min={1}
                max={1500}
                value={wellDepthInput}
                onChange={(e) => setWellDepthInput(e.target.value)}
              />
            </div>
            <div className="selector-field">
              <label htmlFor="well-unit-select">Unit</label>
              <select
                id="well-unit-select"
                value={wellUnit}
                onChange={(e) => {
                  const next = e.target.value;
                  setWellDepthInput((prev) =>
                    next === "m" ? Math.round(prev * 0.3048) : Math.round(prev / 0.3048)
                  );
                  setWellUnit(next);
                }}
              >
                <option value="ft">Feet (ft)</option>
                <option value="m">Metres (m)</option>
              </select>
            </div>
          </div>

          <div className={`sim-result-banner sim-${wellEval.severity}`}>
            <strong>{wellEval.headline}</strong>
            <p>{wellEval.detail}</p>
            <div className="sim-kpis">
              <span>Well Bottom: <strong>{wellEval.wellMeters.toFixed(1)} m</strong></span>
              <span>Buffer vs Median: <strong>{wellEval.bufferP50 >= 0 ? "+" : ""}{wellEval.bufferP50.toFixed(1)} m</strong></span>
              <span>Buffer vs P90 Stress: <strong>{wellEval.bufferP90 >= 0 ? "+" : ""}{wellEval.bufferP90.toFixed(1)} m</strong></span>
            </div>
          </div>
        </div>
      )}

      {subTab === "recharge" && rechargeEval && (
        <div className="sim-body">
          <div className="sim-inputs-grid-3">
            <div className="selector-field">
              <label htmlFor="catchment-area">Catchment / Land Area</label>
              <input
                id="catchment-area"
                type="number"
                min={0.1}
                step={0.5}
                value={areaInput}
                onChange={(e) => setAreaInput(e.target.value)}
              />
            </div>
            <div className="selector-field">
              <label htmlFor="catchment-unit">Unit</label>
              <select
                id="catchment-unit"
                value={areaUnit}
                onChange={(e) => setAreaUnit(e.target.value)}
              >
                <option value="acres">Acres (Farm Land)</option>
                <option value="sqm">Sq. Metres (Roof / Plot)</option>
              </select>
            </div>
            <div className="selector-field">
              <label htmlFor="structure-select">Recharge Structure</label>
              <select
                id="structure-select"
                value={structureId}
                onChange={(e) => setStructureId(e.target.value)}
              >
                {STRUCTURES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="sim-result-banner sim-safe">
            <strong>
              Harvestable Potential: {Math.round(rechargeEval.cubicMeters).toLocaleString()} m³ (
              {(rechargeEval.capturedLitres / 100000).toFixed(2)} Lakh Litres)
            </strong>
            <p>
              Based on {Math.round(rechargeEval.rainMm)} mm expected monsoon rainfall under the active{" "}
              {forecast.rainfall_pct_of_normal}% scenario.
            </p>
            <div className="sim-kpis">
              <span>Equivalent 10,000L Tankers: <strong>{rechargeEval.tankers10k.toLocaleString()}</strong></span>
              <span>Protective Drip Irrigations (1-acre eq.): <strong>{rechargeEval.protectiveIrrigationsAcres.toFixed(1)} cycles</strong></span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
