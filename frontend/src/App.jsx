import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Droplets, Map as MapIcon, BarChart3, Scale, Info, RefreshCw } from "lucide-react";
import {
  clearApiCache,
  fetchBlocks,
  fetchForecast,
  fetchHealth,
  fetchHistory,
  fetchIndiaStatesGeoJson,
  fetchNearestBlock,
  fetchRankings,
  fetchStateBlocksGeoJson,
  fetchStatesSummary,
} from "./api/wellcastApi";
import { getDictionary, LANGUAGES } from "./i18n";
import BlockSelector from "./components/BlockSelector";
import MapView from "./components/MapView";
import RiskBadge from "./components/RiskBadge";
import ScenarioSlider from "./components/ScenarioSlider";
import ForecastChart from "./components/ForecastChart";
import AdvicePanel from "./components/AdvicePanel";
import CropAdvisor from "./components/CropAdvisor";
import WellAndRechargeSimulator from "./components/WellAndRechargeSimulator";
import CompareView from "./components/CompareView";
import PlannerView from "./components/PlannerView";
import DataLimitationsModal from "./components/DataLimitationsModal";

export default function App() {
  const [lang, setLang] = useState("en");
  const [activeTab, setActiveTab] = useState("farmer"); // "farmer" | "compare" | "planner"
  const [scenario, setScenario] = useState("normal");

  const [healthMeta, setHealthMeta] = useState(null);
  const [statesSummary, setStatesSummary] = useState([]);
  const [indiaStatesGeoJson, setIndiaStatesGeoJson] = useState(null);

  const [selectedStateCode, setSelectedStateCode] = useState("ALL");
  const [stateBlocksGeoJson, setStateBlocksGeoJson] = useState(null);
  const [blocks, setBlocks] = useState([]);
  const [selectedDistrict, setSelectedDistrict] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState("");

  const [forecast, setForecast] = useState(null);
  const [history, setHistory] = useState(null);

  const [plannerStateCode, setPlannerStateCode] = useState("ALL");
  const [rankingsDoc, setRankingsDoc] = useState(null);

  const [loadingInit, setLoadingInit] = useState(true);
  const [locating, setLocating] = useState(false);
  const [apiError, setApiError] = useState("");
  const [limitsOpen, setLimitsOpen] = useState(false);

  const t = useMemo(() => getDictionary(lang), [lang]);

  const sortedStatesForDropdown = useMemo(() => {
    return [...statesSummary].sort((a, b) => a.state.localeCompare(b.state));
  }, [statesSummary]);

  const loadInitialData = useCallback(async () => {
    setLoadingInit(true);
    setApiError("");
    try {
      const [meta, stDoc, indiaGj, mhBlocks] = await Promise.all([
        fetchHealth(),
        fetchStatesSummary("normal"),
        fetchIndiaStatesGeoJson(),
        fetchBlocks("MH", "normal"),
      ]);
      setHealthMeta(meta);
      setStatesSummary(stDoc.states || []);
      setIndiaStatesGeoJson(indiaGj);

        // Seed a representative initial block so right-hand advisory panels are populated immediately
        const mhList = mhBlocks.blocks || [];
        const seed =
          mhList.find((b) => b.block_name.toLowerCase() === "baramati") ||
          mhList.find((b) => b.risk_class === "Critical") ||
          mhList[0];
        if (seed) {
          setSelectedBlockId((prev) => prev || seed.block_id);
        }
      } catch (err) {
        setApiError(err.message || "Failed to load WellCast Pan-India API");
      } finally {
        setLoadingInit(false);
      }
    }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Refresh national states summary when drought scenario changes
  useEffect(() => {
    let cancelled = false;
        fetchStatesSummary(scenario)
          .then((doc) => {
            if (!cancelled) setStatesSummary(doc.states || []);
          })
          .catch(() => { });
        return () => {
          cancelled = true;
        };
      }, [scenario]);

    // Lazy-load state blocks GeoJSON & block list when user drills into a state
    useEffect(() => {
      if (selectedStateCode === "ALL") return;
      let cancelled = false;
      Promise.all([
        fetchStateBlocksGeoJson(selectedStateCode),
        fetchBlocks(selectedStateCode, scenario),
      ])
        .then(([gj, blkDoc]) => {
          if (cancelled) return;
          setStateBlocksGeoJson(gj);
          const list = blkDoc.blocks || [];
          setBlocks(list);
          if (list.length > 0 && !selectedBlockId.startsWith(selectedStateCode + "-")) {
            const pick = list.find((b) => b.risk_class !== "Insufficient Data") || list[0];
            if (pick) setSelectedBlockId(pick.block_id);
          }
        })
        .catch((err) => {
          if (!cancelled) setApiError(err.message || "Failed to load state boundaries");
        });
      return () => {
        cancelled = true;
      };
    }, [selectedStateCode, scenario]);

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
        .catch(() => { });
      return () => {
        cancelled = true;
      };
    }, [selectedBlockId]);

    // Load rankings when Planner view, planner state, or scenario changes
    useEffect(() => {
      if (activeTab !== "planner") return;
      let cancelled = false;
      fetchRankings(plannerStateCode, scenario, 400)
        .then((doc) => {
          if (!cancelled) setRankingsDoc(doc);
        })
        .catch((err) => {
          if (!cancelled) setApiError(err.message || "Error loading rankings");
        });
      return () => {
        cancelled = true;
      };
  }, [activeTab, plannerStateCode, scenario]);

    const handleSelectState = useCallback((stCode) => {
      setSelectedDistrict("");
      setSelectedStateCode(stCode);
    }, []);

    const handleLocateMe = useCallback(() => {
      if (!navigator.geolocation) {
        setApiError("Geolocation is not supported by this browser.");
        return;
      }
      setLocating(true);
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          try {
            const res = await fetchNearestBlock(pos.coords.latitude, pos.coords.longitude, scenario);
            if (res?.block) {
              setSelectedDistrict("");
              setSelectedStateCode(res.block.state_code);
              setSelectedBlockId(res.block.block_id);
            }
          } catch (err) {
            setApiError(err.message || "Could not locate nearest block");
          } finally {
            setLocating(false);
          }
        },
        () => {
          setLocating(false);
          setApiError("Location permission denied — select your State and Block from the dropdowns.");
        },
        { timeout: 8000 }
      );
    }, [scenario]);

    const handleInspectFromPlanner = useCallback((blockId, stateCode, district) => {
      setSelectedStateCode(stateCode || blockId.slice(0, 2));
      setSelectedDistrict(district || "");
      setSelectedBlockId(blockId);
      setActiveTab("farmer");
    }, []);

    return (
      <div className="app-shell">
          <header className="topbar no-print">
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
                  aria-selected={activeTab === "compare"}
                  className={`tab-btn ${activeTab === "compare" ? "active" : ""}`}
                  onClick={() => setActiveTab("compare")}
                >
                  <Scale size={15} aria-hidden="true" />
                  <span>Compare Blocks</span>
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
                <div className="error-banner card no-print" role="alert">
                  <div>
                    <strong>{t.errors.apiOfflineTitle}</strong>
                    <p>{apiError}</p>
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
          <div className="loading-card card">Loading All-India groundwater forecasts &amp; state maps…</div>
                ) : activeTab === "planner" ? (
                  <PlannerView
                    statesSummary={statesSummary}
                    plannerStateCode={plannerStateCode}
                    onChangePlannerState={setPlannerStateCode}
                    rankingsDoc={rankingsDoc}
                    scenario={scenario}
                    onChangeScenario={setScenario}
                    onInspectBlock={handleInspectFromPlanner}
                    t={t}
                  />
                ) : activeTab === "compare" ? (
                  <>
                    <ScenarioSlider scenario={scenario} onChangeScenario={setScenario} t={t} />
                    <CompareView statesList={sortedStatesForDropdown} scenario={scenario} t={t} />
                  </>
                ) : (
                  <>
                    <BlockSelector
                      statesList={sortedStatesForDropdown}
                      selectedStateCode={selectedStateCode}
                      onSelectState={handleSelectState}
                      blocks={blocks}
                      selectedDistrict={selectedDistrict}
                      onSelectDistrict={setSelectedDistrict}
                      selectedBlockId={selectedBlockId}
                      onSelectBlock={setSelectedBlockId}
                      onLocateMe={handleLocateMe}
                      locating={locating}
                      t={t}
                    />

                    <div className="farmer-grid">
                        <div className="farmer-left no-print-map-controls">
                          <MapView
                            mode={selectedStateCode === "ALL" ? "india" : "state"}
                            indiaStatesGeoJson={indiaStatesGeoJson}
                            statesSummary={statesSummary}
                            stateBlocksGeoJson={stateBlocksGeoJson}
                            blocks={blocks}
                            selectedStateCode={selectedStateCode}
                            selectedBlockId={selectedBlockId}
                            onSelectState={handleSelectState}
                            onSelectBlock={setSelectedBlockId}
                            t={t}
                          />
                          <ScenarioSlider
                            scenario={scenario}
                            onChangeScenario={setScenario}
                            t={t}
                          />
                          <WellAndRechargeSimulator forecast={forecast} />
                        </div>

                        <div className="farmer-right">
                          {forecast && (
                            <div className="summary-card card">
                              <div className="summary-top">
                                <div>
                                  <span className="eyebrow">
                                    {forecast.state} · {forecast.district} · {forecast.block_id}
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
                          <CropAdvisor forecast={forecast} />
                        </div>
                      </div>
                    </>
        )}
                  </main>

                  <footer className="app-footer no-print">
                    <span>
                      WellCast Pan-India ({healthMeta?.states_indexed || 36} States &amp; UTs ·{" "}
                      {healthMeta?.blocks_indexed?.toLocaleString() || "5,900+"} Sub-Districts) · Public Data: CGWB, GSDA &amp;
                      NASA POWER
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
