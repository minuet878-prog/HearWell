import { useEffect, useState } from "react";
import {
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
const TEXT_COLOR = "#343a40";
// Presentation only (Minty success / warning / danger); the bands themselves come from the API.
const BAND_COLORS = { normal: "#56cc9d", mild_to_moderate: "#ffce67", severe: "#ff7851" };

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

  return (
    <section aria-labelledby="trend-title" className="mb-4">
      <h2 id="trend-title" className="fs-3 mt-3">
        {name} 總分變化
      </h2>
      {/* The summary below and the cards list carry the same information as text. */}
      <div style={{ height: "20rem" }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
          <LineChart data={points} margin={{ top: 16, right: 24, bottom: 8, left: 0 }} accessibilityLayer={false}>
            {levels.map((level, i) => (
              <ReferenceArea
                key={level.code}
                y1={i === 0 ? 0 : levels[i - 1].max}
                y2={level.max}
                fill={BAND_COLORS[level.code] ?? "#cccccc"}
                fillOpacity={0.25}
                label={{ value: level.text, position: "insideTopLeft", fill: TEXT_COLOR, ...FONT }}
              />
            ))}
            <XAxis dataKey="id" tickFormatter={dateOf} tick={{ fill: TEXT_COLOR, ...FONT }} />
            <YAxis domain={[0, top]} allowDecimals={false} tick={{ fill: TEXT_COLOR, ...FONT }} />
            <Tooltip
              contentStyle={FONT}
              labelFormatter={dateOf}
              formatter={(value, _name, item) => [`${value} 分，${item.payload.levelText}`, "總分"]}
            />
            <Line
              dataKey="total"
              stroke={TEXT_COLOR}
              strokeWidth={3}
              dot={{ r: 6, fill: TEXT_COLOR }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="fs-5">{summarize(points)}</p>
    </section>
  );
}
