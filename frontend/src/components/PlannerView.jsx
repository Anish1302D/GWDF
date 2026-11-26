import React, { useMemo, useState } from "react";
import { Download, MapPin } from "lucide-react";
import RiskBadge from "./RiskBadge";

export default function PlannerView({
  rankingsDoc,
  scenario,
  onChangeScenario,
  onInspectBlock,
  t,
}) {
  const [districtFilter, setDistrictFilter] = useState("");
  const [search, setSearch] = useState("");

  const rows = rankingsDoc?.rankings || [];
  const summary = rankingsDoc?.summary || {};

  const districts = useMemo(() => {
    const s = new Set(rows.map((r) => r.district));
    return Array.from(s).sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      const okDist = !districtFilter || r.district === districtFilter;
      const okQ =
        !q ||
        r.block_name.toLowerCase().includes(q) ||
        r.district.toLowerCase().includes(q) ||
        r.block_id.toLowerCase().includes(q);
      return okDist && okQ;
    });
  }, [rows, districtFilter, search]);

  function handleDownloadCsv() {
    const headers = [
      "rank",
      "block_id",
      "district",
      "block_name",
      "scenario",
      "current_depth_mbgl",
      "predicted_depth_mbgl",
      "lower_bound",
      "upper_bound",
      "predicted_yoy_change_mbgl",
      "risk_class",
      "risk_score",
      "well_count",
    ];
    const lines = [
      headers.join(","),
      ...filteredRows.map((r) =>
        [
          r.rank,
          r.block_id,
          `"${r.district}"`,
          `"${r.block_name}"`,
          scenario,
          r.current_depth_mbgl ?? "",
          r.predicted_depth_mbgl ?? "",
          r.lower_bound ?? "",
          r.upper_bound ?? "",
          r.predicted_yoy_change_mbgl ?? "",
          `"${r.risk_class}"`,
          r.risk_score ?? "",
          r.well_count ?? "",
        ].join(",")
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `wellcast_maharashtra_rankings_${scenario}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="planner-section">
      <div className="planner-top card">
        <div>
          <h2>{t.planner.title}</h2>
          <p className="muted-text">{t.planner.subtitle}</p>
        </div>
        <button type="button" className="btn-primary" onClick={handleDownloadCsv}>
          <Download size={16} aria-hidden="true" />
          <span>{t.planner.exportCsv}</span>
        </button>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card card">
          <span className="kpi-label">{t.planner.totalBlocks}</span>
          <strong className="kpi-value">{summary.total_blocks ?? rows.length}</strong>
        </div>
        <div className="kpi-card card kpi-critical">
          <span className="kpi-label">{t.planner.criticalBlocks}</span>
          <strong className="kpi-value">{summary.critical ?? 0}</strong>
        </div>
        <div className="kpi-card card kpi-watch">
          <span className="kpi-label">{t.planner.watchBlocks}</span>
          <strong className="kpi-value">{summary.watch ?? 0}</strong>
        </div>
        <div className="kpi-card card kpi-safe">
          <span className="kpi-label">{t.planner.safeBlocks}</span>
          <strong className="kpi-value">{summary.safe ?? 0}</strong>
        </div>
      </div>

      <div className="planner-filters card">
        <div className="selector-field">
          <label htmlFor="planner-scenario">Scenario</label>
          <select
            id="planner-scenario"
            value={scenario}
            onChange={(e) => onChangeScenario(e.target.value)}
          >
            {["normal", "minus10", "minus20", "minus30"].map((k) => (
              <option key={k} value={k}>
                {t.scenario.stops[k]}
              </option>
            ))}
          </select>
        </div>

        <div className="selector-field">
          <label htmlFor="planner-dist">{t.selectDistrict}</label>
          <select
            id="planner-dist"
            value={districtFilter}
            onChange={(e) => setDistrictFilter(e.target.value)}
          >
            <option value="">{t.allDistricts}</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        <div className="selector-field">
          <label htmlFor="planner-search">{t.selectBlock}</label>
          <input
            id="planner-search"
            type="search"
            placeholder={t.searchBlockPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="table-wrap card">
        <table className="rankings-table">
          <thead>
            <tr>
              <th>{t.planner.colRank}</th>
              <th>{t.planner.colDistrict}</th>
              <th>{t.planner.colBlock}</th>
              <th>{t.planner.colCurrent}</th>
              <th>{t.planner.colPredicted}</th>
              <th>{t.planner.colRange}</th>
              <th>{t.planner.colShift}</th>
              <th>{t.planner.colRisk}</th>
              <th>{t.planner.colScore}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.slice(0, 120).map((r) => {
              const delta = r.predicted_yoy_change_mbgl;
              const deltaTxt =
                delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(2)} m`;
              return (
                <tr key={r.block_id}>
                  <td>#{r.rank}</td>
                  <td>{r.district}</td>
                  <td>
                    <strong>{r.block_name}</strong>
                    <div className="sub-code">{r.block_id}</div>
                  </td>
                  <td>{r.current_depth_mbgl?.toFixed(2) ?? "—"}</td>
                  <td>
                    <strong>{r.predicted_depth_mbgl?.toFixed(2) ?? "—"}</strong>
                  </td>
                  <td className="nowrap">
                    {r.lower_bound != null
                      ? `${r.lower_bound.toFixed(1)} – ${r.upper_bound.toFixed(1)}`
                      : "—"}
                  </td>
                  <td className={delta > 0.5 ? "delta-bad" : delta < -0.3 ? "delta-good" : ""}>
                    {deltaTxt}
                  </td>
                  <td>
                    <RiskBadge
                      riskClass={r.risk_class}
                      label={t.riskClasses[r.risk_class] || r.risk_class}
                      size="sm"
                    />
                  </td>
                  <td>
                    <div className="score-cell">
                      <div className="score-bar-track">
                        <div
                          className="score-bar-fill"
                          style={{ width: `${Math.min(100, Math.max(0, r.risk_score))}%` }}
                        />
                      </div>
                      <span>{r.risk_score?.toFixed(1)}</span>
                    </div>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => onInspectBlock(r.block_id, r.district)}
                    >
                      <MapPin size={14} aria-hidden="true" />
                      <span>{t.planner.inspectOnMap}</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
