import React from "react";
import { CloudRain } from "lucide-react";

const STOPS = ["normal", "minus10", "minus20", "minus30"];

export default function ScenarioSlider({ scenario, onChangeScenario, t }) {
  const activeIdx = Math.max(0, STOPS.indexOf(scenario));

  return (
    <div className="scenario-card card">
      <div className="scenario-header">
        <div className="scenario-title-row">
          <CloudRain size={18} className="accent-icon" aria-hidden="true" />
          <h3>{t.scenario.title}</h3>
        </div>
        <p className="muted-text">{t.scenario.subtitle}</p>
      </div>

      <input
        type="range"
        min={0}
        max={STOPS.length - 1}
        step={1}
        value={activeIdx}
        onChange={(e) => onChangeScenario(STOPS[Number(e.target.value)])}
        className="scenario-range-input"
        aria-label={t.scenario.title}
      />

      <div className="scenario-chips">
        {STOPS.map((key) => (
          <button
            key={key}
            type="button"
            className={`scenario-chip ${scenario === key ? "active" : ""}`}
            onClick={() => onChangeScenario(key)}
          >
            {t.scenario.stops[key]}
          </button>
        ))}
      </div>
    </div>
  );
}
