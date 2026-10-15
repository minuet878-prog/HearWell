import { useEffect, useState } from "react";
import {
  LabelList,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { selectPoints, summarize } from "./trend.js";

const ERROR_TEXT = "趨勢圖暫時無法顯示，下方的紀錄不受影響。";
const FONT = { fontSize: "1rem" };
const TEXT_COLOR = "#212529";
const MUTED_COLOR = "#495057";
const PRIMARY = "#1f4e8c";
// Presentation only; the bands themselves come from the API. Label on band >= 4.5:1.
const BAND_STYLES = {
  normal: { fill: "#e3f4ec", label: "#1e7b55" },
  mild_to_moderate: { fill: "#fff4d6", label: "#8a5a00" },
  severe: { fill: "#feece7", label: "#c23b1c" },
};
const OTHER_BAND = { fill: "#e9ecef", label: TEXT_COLOR };

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

export default function TrendChart() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    // Only the first page: the latest 20 submissions.
    Promise.all([getJson("/api/submissions/"), getJson("/api/questionnaires/")])
      .then(([page, questionnaires]) => setState({ status: "ready", page, questionnaires }))
      .catch(() => setState({ status: "error" }));
  }, []);

  if (state.status === "loading") return null;
  if (state.status === "error") return <p className="fs-5">{ERROR_TEXT}</p>;

  const points = selectPoints(state.page.results);
  if (points.length === 0) return null;

  const { code, name } = state.page.results[0].questionnaire;
  const levels = state.questionnaires.find((q) => q.code === code)?.levels ?? [];
  const top = levels.length > 0 ? levels.at(-1).max : Math.max(1, ...points.map((p) => p.total));
  // Recharts finds the tooltip's point by its x value, so x must be unique (id), not the date:
  // several screenings can share a day.
  const dateOf = (id) => points.find((p) => p.id === id)?.date;
  const latestIndex = points.length - 1;
  const summary = summarize(points);

  const renderDot = ({ cx, cy, index }) => {
    const latest = index === latestIndex;
    return (
      <circle
        key={index}
        cx={cx}
        cy={cy}
        r={latest ? 8 : 6}
        fill={latest ? PRIMARY : "#fff"}
        stroke={PRIMARY}
        strokeWidth={3}
      />
    );
  };

  // Score above each point; below it when the point is near the top so it stays inside the chart.
  const renderScore = ({ x, y, value }) => (
    <text
      className="trend-score"
      x={x}
      y={value >= top * 0.85 ? y + 28 : y - 14}
      textAnchor="middle"
      fill={TEXT_COLOR}
      fontWeight="700"
      style={FONT}
    >
      {value}
    </text>
  );

  return (
    <section aria-labelledby="trend-title" className="mb-4">
      <h2 id="trend-title" className="fs-3">
        {name} 總分變化
      </h2>
      <div className="trend-summary mb-3">
        <p className="mb-1">最近一次（{summary.date}）</p>
        <p className="trend-summary-score mb-1">
          <strong>{summary.total} 分</strong> <span>{summary.levelText}</span>
        </p>
        <p className="mb-0">{summary.change}</p>
      </div>
      <div className="card">
        <div className="card-body">
          {/* The summary box above and the cards list carry the same information as text. */}
          <div style={{ height: "20rem" }} aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
              <LineChart data={points} margin={{ top: 24, right: 16, bottom: 8, left: 16 }} accessibilityLayer={false}>
                {levels.map((level, i) => {
                  const style = BAND_STYLES[level.code] ?? OTHER_BAND;
                  return (
                    <ReferenceArea
                      key={level.code}
                      y1={i === 0 ? 0 : levels[i - 1].max}
                      y2={level.max}
                      fill={style.fill}
                      fillOpacity={1}
                      label={{ value: level.text, position: "insideTopRight", fill: style.label, fontWeight: 600, ...FONT }}
                    />
                  );
                })}
                <XAxis
                  dataKey="id"
                  tickFormatter={dateOf}
                  interval="preserveStartEnd"
                // Space between the plot and the dates; the axis is taller so they are not cut off.
                tickMargin={12}
                height={44}
                  tick={{ fill: MUTED_COLOR, ...FONT }}
                  axisLine={false}
                  tickLine={false}
                />
                {/* No numbers: each point shows its score and the bands show the levels. */}
                <YAxis hide domain={[0, top]} />
                <Tooltip
                  contentStyle={{ ...FONT, borderRadius: "0.5rem" }}
                  labelFormatter={dateOf}
                  formatter={(value, _name, item) => [`${value} 分，${item.payload.levelText}`, "總分"]}
                />
                <Line
                  dataKey="total"
                  stroke={PRIMARY}
                  strokeWidth={3}
                  dot={renderDot}
                  activeDot={false}
                  isAnimationActive={false}
                >
                  <LabelList dataKey="total" content={renderScore} />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </section>
  );
}
