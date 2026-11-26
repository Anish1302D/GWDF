import React from "react";
import { Sprout, Database } from "lucide-react";

export default function AdvicePanel({ forecast, lang, t }) {
  if (!forecast) return null;

  const adviceText =
    forecast.advice?.[lang] || forecast.advice?.en || "";

  return (
    <div className="advice-card card">
      <div className="advice-header">
        <Sprout size={19} className="accent-icon" aria-hidden="true" />
        <h3>{t.advice.title}</h3>
      </div>

      <p className="advice-body">{adviceText}</p>

      <div className="advice-meta-row">
        <span className="meta-pill">
          <Database size={13} aria-hidden="true" />
          {t.forecastCard.wellsMonitored}: <strong>{forecast.well_count ?? 0}</strong>
        </span>
        <span className="meta-note">{t.advice.sourceNote}</span>
      </div>
    </div>
  );
}
