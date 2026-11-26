import React, { useMemo } from "react";
import {
  ComposedChart,
  Line,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export default function ForecastChart({ history, forecast, t }) {
  const depthSeries = useMemo(() => {
    const levels = history?.water_levels || [];
    const pts = levels.map((item) => ({
      label: `${item.obs_date.slice(0, 4)} ${item.season === "pre-monsoon" ? "Pre" : "Post"}`,
      historicalDepth: item.depth_mbgl,
      forecastDepth: null,
      bandRange: null,
    }));

    if (forecast && forecast.predicted_depth_mbgl != null) {
      if (pts.length > 0) {
        // Connect last observed point smoothly to forecast segment
        const last = pts[pts.length - 1];
        last.forecastDepth = last.historicalDepth;
      }
      const fLabel = forecast.forecast_season
        .replace("-pre-monsoon", " Pre*")
        .replace("-post-monsoon", " Post*");
      pts.push({
        label: fLabel,
        historicalDepth: null,
        forecastDepth: forecast.predicted_depth_mbgl,
        bandRange: [forecast.lower_bound, forecast.upper_bound],
        lower: forecast.lower_bound,
        upper: forecast.upper_bound,
      });
    }
    return pts;
  }, [history, forecast]);

  const rainSeries = useMemo(() => {
    return (history?.rainfall_seasonal || []).slice(-8).map((r) => ({
      year: r.period.slice(0, 4),
      actual: r.rainfall_mm,
      normal: r.normal_mm,
    }));
  }, [history]);

  if (!depthSeries.length) {
    return null;
  }

  return (
    <div className="charts-stack">
      <div className="chart-card card">
        <div className="chart-header">
          <h3>{t.chart.title}</h3>
          <span className="chart-subnote">{t.forecastCard.deeperWorseNote}</span>
        </div>
        <div className="chart-box">
          <ResponsiveContainer width="100%" height={265}>
            <ComposedChart data={depthSeries} margin={{ top: 10, right: 18, left: 4, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis
                reversed
                domain={[0, "auto"]}
                tick={{ fontSize: 11 }}
                unit=" m"
                width={48}
              />
              <Tooltip
                formatter={(val, name) => {
                  if (Array.isArray(val)) {
                    return [`${val[0]} – ${val[1]} m bgl`, t.chart.confidence];
                  }
                  return [`${val} m bgl`, name];
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area
                type="monotone"
                dataKey="bandRange"
                name={t.chart.confidence}
                stroke="#DC2626"
                strokeOpacity={0.35}
                fill="#FCA5A5"
                fillOpacity={0.45}
              />
              <Line
                type="monotone"
                dataKey="historicalDepth"
                name={t.chart.historical}
                stroke="#0284C7"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="forecastDepth"
                name={t.chart.predicted}
                stroke="#DC2626"
                strokeWidth={2.8}
                strokeDasharray="5 4"
                dot={{ r: 5 }}
                connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {rainSeries.length > 0 && (
        <div className="chart-card card">
          <h3>{t.chart.monsoonTitle}</h3>
          <div className="chart-box-sm">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={rainSeries} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={46} />
                <Tooltip formatter={(val) => `${val} mm`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="actual" name="Observed Monsoon (mm)" fill="#0EA5E9" radius={[3, 3, 0, 0]} />
                <Bar dataKey="normal" name="12-Yr Normal (mm)" fill="#CBD5E1" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
