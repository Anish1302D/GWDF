import React from "react";
import { X, Info } from "lucide-react";

export default function DataLimitationsModal({ open, onClose, healthMeta }) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="limits-title">
      <div className="modal-panel card">
        <div className="modal-header">
          <div className="modal-title-row">
            <Info size={20} className="accent-icon" aria-hidden="true" />
            <h2 id="limits-title">Pan-India Data Sources, AI Methodology &amp; Honest Caveats</h2>
          </div>
          <button type="button" className="icon-close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="modal-content">
          <h4>1. Authentic Nationwide Datasets Used</h4>
          <ul>
            <li>
              <strong>Pan-India Groundwater Monitoring Network (Target):</strong> Central Ground Water Board (CGWB)
              Manual Quarterly Monitoring Wells across all Indian States &amp; UTs (1991–2025, 63 state datasets)
              plus GSDA-Maharashtra (1970–2025) via the Government of India National Water Data Portal (NWIC).
            </li>
            <li>
              <strong>All-India Monthly Precipitation Grid (Predictor):</strong> NASA POWER Agroclimatology (
              <code>PRECTOTCORR</code>, 2012–2025) across 172 nationwide 1.5° hydro-climatic grid cells benchmarked
              against 2013–2024 monthly normals.
            </li>
            <li>
              <strong>Administrative Boundaries:</strong> Census of India / Local Government Directory (LGD)
              All-India State &amp; Sub-District (Block / Tehsil / Taluka / Mandal) GeoJSON boundaries (
              <code>{healthMeta?.blocks_indexed?.toLocaleString() || "5,900+"}</code> units across{" "}
              <code>{healthMeta?.states_indexed || 36}</code> States &amp; UTs).
            </li>
          </ul>

          <h4>2. Forecasting &amp; Conformal Uncertainty Methodology</h4>
          <ul>
            <li>
              <strong>Dual Season-Specialist Monotone XGBoost + CQR:</strong> Separate drawdown and recharge
              specialists trained with strictly causal expanding-window seasonal equilibrium features and rainfall
              monotonicity constraints, evaluated on an untouched chronological holdout year.
            </li>
            <li>
              Active Model: <code>{healthMeta?.model_version || "xgb-dual-specialist-cqr"}</code> · Forecasted Units:{" "}
              <code>{healthMeta?.blocks_forecasted?.toLocaleString() || "All eligible blocks"}</code>.
            </li>
            <li>
              <strong>State-Aware Aquifer Risk Thresholds:</strong> Combines state-calibrated hydrogeological depth
              percentiles (accounting for shallow hard-rock peninsular vs deep Indo-Gangetic alluvial aquifers) with
              universal drawdown velocity rules.
            </li>
          </ul>

          <h4>3. Limitations &amp; Responsible Use</h4>
          <ul>
            <li>
              <strong>Zero Fabricated Data:</strong> Sub-districts with fewer than 4 historical seasonal CGWB
              observations (such as steep Himalayan terrain or unmonitored islands) are explicitly marked{" "}
              <em>Insufficient Data</em> rather than filled with synthetic predictions.
            </li>
            <li>
              <strong>Decision Support Only:</strong> Block medians and crop/recharge calculators guide seasonal
              planning and do not substitute for site-specific hydrogeological surveys or official CGWB advisories.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
