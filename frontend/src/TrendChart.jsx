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

import { chartDays, selectPoints } from "./trend.js";

const LOADING_TEXT = "趨勢圖載入中…"; // the same text is on the page before this script runs
const ERROR_TEXT = "趨勢圖暫時無法顯示，下方的紀錄不受影響。";
// Dates are plain digits/slashes, not CJK text, so they stay on the system font stack (not
// Noto Sans TC from #108): its wider glyphs shifted the SVG tick-label math enough to overflow
// the chart edge by a couple of px (minTickGap / preserveStartEnd assume the old metrics).
const FONT = {
  fontSize: "1rem",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
};
const TEXT_COLOR = "#212529";
const MUTED_COLOR = "#495057";
const PRIMARY = "#1f4e8c";
// Presentation only, by level colour (ADR 0007's three); the bands and each level's colour come
// from the API. The level names under the chart (trend_chart.html) use the same fills.
const BAND_FILLS = {
  normal: "#e3f4ec",
  mild_to_moderate: "#fff4d6",
  severe: "#feece7",
};
const OTHER_BAND_FILL = "#e9ecef";
// Hearing aid status (spec 4b): filled circle / hollow square / hollow triangle; the legend under
// the chart (trend_chart.html) draws the same shapes.
// Each status is its own series (phase9_ui_refresh_2_data.md 4.1): unaided solid, aided dashed,
// unrecorded points only, so no line joins records taken under different conditions.
const STATUSES = [
  { wearing: false, key: "unaided", shape: "circle", text: "沒戴", line: {} },
  { wearing: true, key: "aided", shape: "square", text: "有戴", line: { strokeDasharray: "8 6" } },
  { wearing: null, key: "unrecorded", shape: "triangle", text: "未記錄", line: null },
];

// size is the half width; data-* keep the centre for tests (shapes have no cx/cy of their own).
function Shape({ shape, x, y, size, status }) {
  const common = {
    className: "trend-dot",
    stroke: PRIMARY,
    strokeWidth: 3,
    "data-cx": x,
    "data-cy": y,
    "data-size": size,
    "data-status": status,
  };
  if (shape === "circle") return <circle {...common} cx={x} cy={y} r={size} fill={PRIMARY} />;
  if (shape === "square") {
    return <rect {...common} x={x - size} y={y - size} width={size * 2} height={size * 2} fill="#fff" />;
  }
  const points = `${x},${y - size * 1.2} ${x + size * 1.1},${y + size * 0.8} ${x - size * 1.1},${y + size * 0.8}`;
  return <polygon {...common} points={points} fill="#fff" />;
}

// Recharts measures each date once and keeps the width, so measure in Noto Sans TC (layout.html):
// with the fallback font's width the first date sticks out of the chart. At most 3 s, then draw.
function fontsReady() {
  return Promise.race([document.fonts.ready, new Promise((resolve) => setTimeout(resolve, 3000))]);
}

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

export default function TrendChart({ code }) {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    // Only the first page: the latest 20 submissions.
    Promise.all([getJson("/api/submissions/"), getJson("/api/questionnaires/"), fontsReady()])
      .then(([page, questionnaires]) => setState({ status: "ready", page, questionnaires }))
      .catch(() => setState({ status: "error" }));
  }, []);

  // Rendered into the chart's box (#trend-plot), which keeps its height whatever is in it.
  // Screen readers skip the loading text and the chart, but hear when the chart cannot show.
  if (state.status === "loading") {
    return (
      <p className="trend-plot-message" aria-hidden="true">
        {LOADING_TEXT}
      </p>
    );
  }
  if (state.status === "error") return <p className="trend-plot-message text-xl/normal">{ERROR_TEXT}</p>;

  const points = selectPoints(state.page.results, code);
  if (points.length === 0) return null;

  const levels = state.questionnaires.find((q) => q.code === code)?.levels ?? [];
  const top = levels.length > 0 ? levels.at(-1).max : Math.max(1, ...points.map((p) => p.total));
  const days = chartDays(points);
  const latestIndex = days.length - 1;
  const latestWearing = points.at(-1).wearing;

  // The latest point is only bigger: filled vs hollow already means the hearing aid status.
  // Each series calls this for every day; only days with a record of its status get a shape.
  const renderDot =
    (status) =>
    ({ cx, cy, index, payload }) =>
      payload[status.key] !== null ? (
        <Shape
          key={index}
          shape={status.shape}
          status={status.key}
          x={cx}
          y={cy}
          size={index === latestIndex && status.wearing === latestWearing ? 9 : 6}
        />
      ) : (
        <g key={index} />
      );
  // HHIE-S and THI totals are even (every answer is 0, 2 or 4), so halfway between two levels is
  // the lower level's top + 1 (spec 4.4): 9 and 25, never on a score. Only they have this chart.
  const bandEdge = (i) => (i === levels.length - 1 ? levels[i].max : levels[i].max + 1);

  // Score above each point; below it when the point is near the top so it stays inside the chart.
  // Each series has an empty slot for the other statuses' records: no label there.
  const renderScore = ({ x, y, value }) =>
    value == null ? null : (
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

  // The summary box above the chart and the cards list carry the same information as text.
  return (
    <div className="h-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 600, height: 320 }}>
        <LineChart data={days} margin={{ top: 24, right: 16, bottom: 8, left: 16 }} accessibilityLayer={false}>
          {levels.map((level, i) => (
            <ReferenceArea
              key={level.code}
              y1={i === 0 ? 0 : bandEdge(i - 1)}
              y2={bandEdge(i)}
              fill={BAND_FILLS[level.color] ?? OTHER_BAND_FILL}
              fillOpacity={1}
            />
          ))}
          <XAxis
            // One column per day (spec 4.1), so the date is unique and is the label itself.
            dataKey="date"
            interval="preserveStartEnd"
            // At least 1.5rem (27px at the 18px base) between dates (spec 4.3).
            minTickGap={27}
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
            formatter={(value, _name, item) => {
              const key = item.dataKey;
              const status = STATUSES.find((s) => s.key === key);
              // On a day with several records, each one names its time (spec 4.3).
              const time = item.payload.count > 1 ? `（${item.payload[`${key}Time`]}）` : "";
              return [`${value} 分，${item.payload[`${key}Level`]}，助聽器：${status.text}${time}`, "總分"];
            }}
          />
          {STATUSES.map((status) => (
            <Line
              key={status.key}
              className={`trend-line-${status.key}`}
              dataKey={status.key}
              stroke={status.line ? PRIMARY : "none"}
              strokeWidth={3}
              {...status.line}
              // Skip the other statuses' records, so the line joins this status's points.
              connectNulls
              dot={renderDot(status)}
              activeDot={false}
              isAnimationActive={false}
            >
              <LabelList dataKey={status.key} content={renderScore} />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
