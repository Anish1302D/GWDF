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
            <h2 id="limits-title">Data Sources, Methodology & Honest Caveats</h2>
          </div>
          <button type="button" className="icon-close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="modal-content">
          <h4>1. Verified Public Datasets Used</h4>
          <ul>
            <li>
              <strong>Groundwater Monitoring Wells (Target):</strong> Central Ground Water Board (CGWB) Manual
              Quarterly Readings (1991–2025) &amp; Groundwater Surveys and Development Agency (GSDA-Maharashtra,
              1970–2025) via the Government of India National Water Data Portal (NWIC).
            </li>
            <li>
              <strong>Monthly Precipitation &amp; Normals (Predictor):</strong> NASA POWER Agroclimatology Gridded
              Monthly Precipitation (<code>PRECTOTCORR</code>, 2012–2025) across all 36 Maharashtra districts,
              benchmarked against 2013–2024 monthly normals.
            </li>
            <li>
              <strong>Block Administrative Boundaries:</strong> Census of India / LGD Maharashtra Sub-District
              (Taluka) GeoJSON (356 canonical blocks across 36 districts).
            </li>
          </ul>

          <h4>2. Forecasting &amp; Uncertainty Methodology</h4>
          <ul>
            <li>
              Evaluated strictly on a <strong>chronological future holdout year</strong> (zero random time-series
              splits) benchmarked against a Seasonal Naive baseline.
            </li>
            <li>
              Active Model Version: <code>{healthMeta?.model_version || "xgb-residual-v1"}</code> · Forecast Target:{" "}
              <code>{healthMeta?.forecast_season || "Upcoming Season"}</code>.
            </li>
            <li>
              <strong>P10–P90 Confidence Band:</strong> Shows an 80% uncertainty range rather than a single
              deterministic point prediction.
            </li>
          </ul>

          <h4>3. Limitations &amp; Responsible Use</h4>
          <ul>
            <li>
              <strong>Zero Fabricated Data:</strong> Blocks with fewer than 4 historical seasonal observations are
              explicitly marked <em>Insufficient Data</em> rather than filled with synthetic numbers.
            </li>
            <li>
              <strong>Spatial Resolution:</strong> Block water levels represent the median of public monitoring wells
              within each taluka; local borewell depths can vary due to fractured Deccan basalt geology and localized
              pumping. Rainfall is mapped from district-level agroclimatology grids.
            </li>
            <li>
              <strong>Decision Support Only:</strong> Forecasts complement — and do not replace — site-specific
              hydrogeological surveys or official GSDA/CGWB advisories.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
