import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Droplets, Map as MapIcon, BarChart3, Info, RefreshCw } from "lucide-react";
import {
  clearApiCache,
  fetchBlocks,
  fetchForecast,
  fetchGeoJson,
  fetchHealth,
  fetchHistory,
  fetchRankings,
} from "./api/wellcastApi";
import { getDictionary, LANGUAGES } from "./i18n";
import BlockSelector from "./components/BlockSelector";
import MapView from "./components/MapView";
import RiskBadge from "./components/RiskBadge";
import ScenarioSlider from "./components/ScenarioSlider";
import ForecastChart from "./components/ForecastChart";
import AdvicePanel from "./components/AdvicePanel";
import PlannerView from "./components/PlannerView";
import DataLimitationsModal from "./components/DataLimitationsModal";

export default function App() {
  const [lang, setLang] = useState("en");
  const [activeTab, setActiveTab] = useState("farmer"); // "farmer" | "planner"
  const [scenario, setScenario] = useState("normal");

  const [healthMeta, setHealthMeta] = useState(null);
  const [geoJson, setGeoJson] = useState(null);
  const [blocks, setBlocks] = useState([]);
  const [selectedDistrict, setSelectedDistrict] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState("");

  const [forecast, setForecast] = useState(null);
  const [history, setHistory] = useState(null);
  const [rankingsDoc, setRankingsDoc] = useState(null);

  const [loadingInit, setLoadingInit] = useState(true);
  const [apiError, setApiError] = useState("");
  const [limitsOpen, setLimitsOpen] = useState(false);

  const t = useMemo(() => getDictionary(lang), [lang]);

  const loadInitialData = useCallback(async () => {
    setLoadingInit(true);
    setApiError("");
    try {
      const [meta, blocksRes, gj] = await Promise.all([
        fetchHealth(),
        fetchBlocks("normal"),
        fetchGeoJson(),
      ]);
      setHealthMeta(meta);
      setGeoJson(gj);
      const list = blocksRes.blocks || [];
      setBlocks(list);

      // Default to a representative high-interest block (e.g., Baramati in Pune or first Watch/Critical block)
      const preferred =
        list.find((b) => b.block_name.toLowerCase() === "baramati") ||
        list.find((b) => b.risk_class === "Critical") ||
        list[0];
      if (preferred) {
        setSelectedBlockId((prev) => prev || preferred.block_id);
      }
    } catch (err) {
      setApiError(err.message || "Failed to load WellCast API");
    } finally {
      setLoadingInit(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Refresh map block risk classes whenever rainfall scenario changes
  useEffect(() => {
    let cancelled = false;
    fetchBlocks(scenario)
      .then((res) => {
        if (!cancelled) {
          setBlocks(res.blocks || []);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [scenario]);

  // Load selected block forecast when block or scenario changes
  useEffect(() => {
    if (!selectedBlockId) return;
    let cancelled = false;
    fetchForecast(selectedBlockId, scenario)
      .then((f) => {
        if (!cancelled) setForecast(f);
      })
      .catch((err) => {
        if (!cancelled) setApiError(err.message || "Error loading block forecast");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedBlockId, scenario]);

  // Load selected block historical series when block changes
  useEffect(() => {
    if (!selectedBlockId) return;
    let cancelled = false;
    fetchHistory(selectedBlockId)
      .then((h) => {
        if (!cancelled) setHistory(h);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedBlockId]);

  // Load rankings when Planner view or scenario changes
  useEffect(() => {
    if (activeTab !== "planner") return;
    let cancelled = false;
    fetchRankings(scenario, 400)
      .then((doc) => {
        if (!cancelled) setRankingsDoc(doc);
      })
      .catch((err) => {
        if (!cancelled) setApiError(err.message || "Error loading rankings");
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, scenario]);

  const handleInspectFromPlanner = useCallback((blockId, district) => {
    setSelectedDistrict(district || "");
    setSelectedBlockId(blockId);
    setActiveTab("farmer");
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-logo">
            <Droplets size={22} aria-hidden="true" />
          </div>
          <div>
            <h1>{t.appTitle}</h1>
            <p className="brand-subtitle">{t.appSubtitle}</p>
          </div>
        </div>

        <nav className="topbar-controls" aria-label="Primary Controls">
          <div className="view-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "farmer"}
              className={`tab-btn ${activeTab === "farmer" ? "active" : ""}`}
              onClick={() => setActiveTab("farmer")}
            >
              <MapIcon size={15} aria-hidden="true" />
              <span>{t.farmerView}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "planner"}
              className={`tab-btn ${activeTab === "planner" ? "active" : ""}`}
              onClick={() => setActiveTab("planner")}
            >
              <BarChart3 size={15} aria-hidden="true" />
              <span>{t.plannerView}</span>
            </button>
          </div>

          <div className="lang-switcher" role="group" aria-label="Language selector">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`lang-btn ${lang === l.code ? "active" : ""}`}
                onClick={() => setLang(l.code)}
              >
                {l.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="btn-outline"
            onClick={() => setLimitsOpen(true)}
          >
            <Info size={15} aria-hidden="true" />
            <span>{t.dataAndLimits}</span>
          </button>
        </nav>
      </header>

      <main className="main-container">
        {apiError && (
          <div className="error-banner card" role="alert">
            <div>
              <strong>{t.errors.apiOfflineTitle}</strong>
              <p>{apiError} — {t.errors.apiOfflineBody}</p>
            </div>
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                clearApiCache();
                loadInitialData();
              }}
            >
              <RefreshCw size={15} aria-hidden="true" />
              <span>{t.errors.retry}</span>
            </button>
          </div>
        )}

        {loadingInit ? (
          <div className="loading-card card">Loading Maharashtra block forecasts &amp; boundaries…</div>
        ) : activeTab === "planner" ? (
          <PlannerView
            rankingsDoc={rankingsDoc}
            scenario={scenario}
            onChangeScenario={setScenario}
            onInspectBlock={handleInspectFromPlanner}
            t={t}
          />
        ) : (
          <>
            <BlockSelector
              blocks={blocks}
              selectedDistrict={selectedDistrict}
              onSelectDistrict={setSelectedDistrict}
              selectedBlockId={selectedBlockId}
              onSelectBlock={setSelectedBlockId}
              t={t}
            />

            <div className="farmer-grid">
              <div className="farmer-left">
                <MapView
                  geoJson={geoJson}
                  blocks={blocks}
                  selectedBlockId={selectedBlockId}
                  onSelectBlock={setSelectedBlockId}
                  t={t}
                />
                <ScenarioSlider
                  scenario={scenario}
                  onChangeScenario={setScenario}
                  t={t}
                />
              </div>

              <div className="farmer-right">
                {forecast && (
                  <div className="summary-card card">
                    <div className="summary-top">
                      <div>
                        <span className="eyebrow">
                          {forecast.district} · {forecast.block_id}
                        </span>
                        <h2>{forecast.block_name}</h2>
                      </div>
                      <RiskBadge
                        riskClass={forecast.risk_class}
                        label={t.riskClasses[forecast.risk_class] || forecast.risk_class}
                        size="lg"
                      />
                    </div>

                    {forecast.risk_class === "Insufficient Data" ? (
                      <div className="insufficient-notice">
                        <strong>{t.errors.insufficientTitle}</strong>
                        <p>{t.errors.insufficientBody}</p>
                      </div>
                    ) : (
                      <div className="metrics-strip">
                        <div className="metric-box">
                          <span className="metric-label">{t.forecastCard.predictedDepth}</span>
                          <strong className="metric-main">
                            {forecast.predicted_depth_mbgl?.toFixed(2)} m
                          </strong>
                          <span className="metric-sub">{t.forecastCard.mbglUnit}</span>
                        </div>

                        <div className="metric-box">
                          <span className="metric-label">{t.forecastCard.confidenceBand}</span>
                          <strong className="metric-secondary">
                            {forecast.lower_bound?.toFixed(1)} – {forecast.upper_bound?.toFixed(1)} m
                          </strong>
                          <span className="metric-sub">{forecast.forecast_season}</span>
                        </div>

                        <div className="metric-box">
                          <span className="metric-label">{t.forecastCard.currentDepth}</span>
                          <strong className="metric-secondary">
                            {forecast.current_depth_mbgl?.toFixed(2)} m
                          </strong>
                          <span className="metric-sub">
                            {t.forecastCard.yoyChange}:{" "}
                            {forecast.predicted_yoy_change_mbgl > 0 ? "+" : ""}
                            {forecast.predicted_yoy_change_mbgl?.toFixed(2)} m
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <AdvicePanel forecast={forecast} lang={lang} t={t} />
                <ForecastChart history={history} forecast={forecast} t={t} />
              </div>
            </div>
          </>
        )}
      </main>

      <footer className="app-footer">
        <span>
          WellCast · Public Data: CGWB, GSDA-Maharashtra (NWIC) &amp; NASA POWER Agroclimatology · Built on AWS (
          <code>ap-south-1</code>)
        </span>
        <button type="button" className="footer-link-btn" onClick={() => setLimitsOpen(true)}>
          {t.dataAndLimits}
        </button>
      </footer>

      <DataLimitationsModal
        open={limitsOpen}
        onClose={() => setLimitsOpen(false)}
        healthMeta={healthMeta}
      />
    </div>
  );
}
