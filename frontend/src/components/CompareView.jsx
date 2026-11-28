import React, { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Scale } from "lucide-react";
import { fetchBlocks, fetchForecast, fetchHistory } from "../api/wellcastApi";
import RiskBadge from "./RiskBadge";

const LINE_COLORS = ["#0284C7", "#DC2626", "#16A34A"];

export default function CompareView({ statesList, scenario, t }) {
  const [slots, setSlots] = useState([
    { stateCode: "MH", blockId: "" },
    { stateCode: "PB", blockId: "" },
    { stateCode: "RJ", blockId: "" },
  ]);
  const [blocksByState, setBlocksByState] = useState({});
  const [slotDetails, setSlotDetails] = useState([null, null, null]);

  // Load state block lists as needed
  useEffect(() => {
    slots.forEach((slot) => {
      if (!slot.stateCode || blocksByState[slot.stateCode]) return;
      fetchBlocks(slot.stateCode, "normal")
        .then((res) => {
          const list = res.blocks || [];
          setBlocksByState((prev) => ({ ...prev, [slot.stateCode]: list }));
        })
        .catch(() => {});
    });
  }, [slots, blocksByState]);

  // Auto-select first forecasted block when state list arrives
  useEffect(() => {
    setSlots((prev) =>
      prev.map((slot) => {
        if (slot.blockId) return slot;
        const list = blocksByState[slot.stateCode] || [];
        const pick = list.find((b) => b.risk_class !== "Insufficient Data") || list[0];
        return pick ? { ...slot, blockId: pick.block_id } : slot;
      })
    );
  }, [blocksByState]);

  // Fetch forecast + history for each selected blockId & scenario
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      slots.map(async (slot) => {
        if (!slot.blockId) return null;
        try {
          const [f, h] = await Promise.all([
            fetchForecast(slot.blockId, scenario),
            fetchHistory(slot.blockId),
          ]);
          return { forecast: f, history: h };
        } catch {
          return null;
        }
      })
    ).then((res) => {
      if (!cancelled) setSlotDetails(res);
    });
    return () => {
      cancelled = true;
    };
  }, [slots, scenario]);

  const mergedChartData = useMemo(() => {
    const byDate = new Map();
    slotDetails.forEach((item, idx) => {
      if (!item?.history?.water_levels) return;
      for (const w of item.history.water_levels) {
        const key = `${w.obs_date.slice(0, 4)} ${w.season === "pre-monsoon" ? "Pre" : "Post"}`;
        const row = byDate.get(key) || { period: key, sortKey: w.obs_date };
        row[`b${idx}`] = w.depth_mbgl;
        byDate.set(key, row);
      }
      if (item.forecast?.predicted_depth_mbgl != null) {
        const fKey = `${item.forecast.forecast_season
          .replace("-pre-monsoon", " Pre*")
          .replace("-post-monsoon", " Post*")}`;
        const fRow = byDate.get(fKey) || { period: fKey, sortKey: "9999-99-99" };
        fRow[`b${idx}`] = item.forecast.predicted_depth_mbgl;
        byDate.set(fKey, fRow);
      }
    });
    return Array.from(byDate.values()).sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  }, [slotDetails]);

  return (
    <section className="compare-section">
      <div className="card">
        <div className="scenario-title-row">
          <Scale size={20} className="accent-icon" />
          <div>
            <h2>Cross-India Aquifer Comparison Studio</h2>
            <p className="muted-text">
              Compare historical trajectories, predicted depths, and drought sensitivity across up to 3 blocks in any Indian states
            </p>
          </div>
        </div>
      </div>

      <div className="compare-slots-grid">
        {slots.map((slot, idx) => {
          const stBlocks = blocksByState[slot.stateCode] || [];
          const detail = slotDetails[idx]?.forecast;
          return (
            <div key={idx} className="card compare-slot-card" style={{ borderTop: `4px solid ${LINE_COLORS[idx]}` }}>
              <div className="compare-selectors">
                <div className="selector-field">
                  <label>State / UT #{idx + 1}</label>
                  <select
                    value={slot.stateCode}
                    onChange={(e) => {
                      const nextSt = e.target.value;
                      setSlots((prev) =>
                        prev.map((s, i) => (i === idx ? { stateCode: nextSt, blockId: "" } : s))
                      );
                    }}
                  >
                    {statesList.map((st) => (
                      <option key={st.state_code} value={st.state_code}>
                        {st.state}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="selector-field">
                  <label>Block / Sub-District</label>
                  <select
                    value={slot.blockId}
                    onChange={(e) => {
                      const nextBid = e.target.value;
                      setSlots((prev) =>
                        prev.map((s, i) => (i === idx ? { ...s, blockId: nextBid } : s))
                      );
                    }}
                  >
                    {stBlocks.map((b) => (
                      <option key={b.block_id} value={b.block_id}>
                        {b.block_name} ({b.district})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {detail && (
                <div className="compare-metrics">
                  <div className="compare-head-row">
                    <div>
                      <strong>{detail.block_name}</strong>
                      <div className="sub-code">
                        {detail.district}, {detail.state}
                      </div>
                    </div>
                    <RiskBadge
                      riskClass={detail.risk_class}
                      label={t.riskClasses[detail.risk_class] || detail.risk_class}
                      size="sm"
                    />
                  </div>
                  <div className="compare-kv">
                    <span>Forecast Depth:</span>
                    <strong>
                      {detail.predicted_depth_mbgl != null ? `${detail.predicted_depth_mbgl.toFixed(2)} m` : "N/A"}
                    </strong>
                  </div>
                  <div className="compare-kv">
                    <span>80% Range (P10–P90):</span>
                    <strong>
                      {detail.lower_bound != null
                        ? `${detail.lower_bound.toFixed(1)} – ${detail.upper_bound.toFixed(1)} m`
                        : "N/A"}
                    </strong>
                  </div>
                  <div className="compare-kv">
                    <span>Current Observed:</span>
                    <strong>
                      {detail.current_depth_mbgl != null ? `${detail.current_depth_mbgl.toFixed(2)} m` : "N/A"}
                    </strong>
                  </div>
                  <div className="compare-kv">
                    <span>5-Yr Depletion Trend:</span>
                    <strong>
                      {detail.depth_trend_5yr != null
                        ? `${detail.depth_trend_5yr > 0 ? "+" : ""}${detail.depth_trend_5yr.toFixed(2)} m/yr`
                        : "N/A"}
                    </strong>
                  </div>
                  <div className="compare-kv">
                    <span>Normal Monsoon Rain:</span>
                    <strong>{Math.round(detail.normal_monsoon_mm || 0)} mm</strong>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {mergedChartData.length > 0 && (
        <div className="card">
          <h3>Multi-Region Groundwater Depth Trajectory (m bgl — Inverted Depth Axis)</h3>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={mergedChartData} margin={{ top: 12, right: 20, left: 6, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis reversed domain={[0, "auto"]} unit=" m" width={52} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(val) => `${val} m bgl`} />
              <Legend />
              {slotDetails.map((item, idx) =>
                item?.forecast ? (
                  <Line
                    key={idx}
                    type="monotone"
                    dataKey={`b${idx}`}
                    name={`${item.forecast.block_name} (${item.forecast.state_code})`}
                    stroke={LINE_COLORS[idx]}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                ) : null
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
