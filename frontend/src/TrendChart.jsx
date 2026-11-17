import { useEffect, useState } from "react";
import {
  DefaultZIndexes,
  LabelList,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  useChartWidth,
  usePlotArea,
  useXAxisScale,
  XAxis,
  YAxis,
  ZIndexLayer,
} from "recharts";

import { chartDays, fittingDays, selectPoints } from "./trend.js";

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
// Presentation only, by level colour (ADR 0007's three) and shade; the bands, each level's colour
// and shade come from the API. The level names under the chart (trend_chart.html) use the same
// fills. "deep": the higher of two levels sharing a colour, so THI's five bands stay apart.
const BAND_FILLS = {
  normal: { pale: "#e3f4ec" },
  mild_to_moderate: { pale: "#fff4d6", deep: "#f9dd96" },
  severe: { pale: "#feece7", deep: "#f6c3b3" },
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

// #650 (spec #644 R2, the #645 mockup's A): 開始戴 in a small white box above the plot, in rem so
// it grows with the text: three characters and 0.5rem each side, a gap that clears the biggest
// point at the top score. The plot starts lower to make room only when the line is drawn: the
// box, the gap and 0.25rem above the box.
const FITTING_BOX = { width: 4, height: 1.75, gap: 0.75 };
const FITTING_TOP = FITTING_BOX.height + FITTING_BOX.gap + 0.25;

// The line on the fitting day: midway between the records around it, as the axis has one column
// per record day, not a time scale. Its look in site.css (.trend-fitting-*): neutral colours,
// never a level's, the dashes and the box's rounded corners. Under the score lines and points.
function FittingLine({ between, rem }) {
  const xScale = useXAxisScale();
  const plot = usePlotArea();
  const chartWidth = useChartWidth();
  if (!xScale || !plot) return null;
  const x = (xScale(between[0]) + xScale(between[1])) / 2;
  // Narrower only on a chart too narrow for it (a 320px phone at 200% text): 開始戴 still fits.
  // 1px clear of each edge, so the frame's stroke is not cut off.
  const width = Math.min(FITTING_BOX.width * rem, chartWidth - 2);
  const height = FITTING_BOX.height * rem;
  // Centred over the line, kept inside the chart near its edges.
  const boxX = Math.min(Math.max(x - width / 2, 1), chartWidth - width - 1);
  const boxY = plot.y - FITTING_BOX.gap * rem - height;
  return (
    <ZIndexLayer zIndex={DefaultZIndexes.line - 1}>
      <g className="trend-fitting">
        <line
          className="trend-fitting-line"
          x1={x}
          x2={x}
          y1={boxY + height}
          y2={plot.y + plot.height}
        />
        <rect className="trend-fitting-box" x={boxX} y={boxY} width={width} height={height} />
        <text
          className="trend-fitting-text"
          x={boxX + width / 2}
          y={boxY + height / 2}
          textAnchor="middle"
          dominantBaseline="central"
        >
          開始戴
        </text>
      </g>
    </ZIndexLayer>
  );
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

export default function TrendChart({ code, fittedOn }) {
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
      <p className="trend-plot-message loading-message" aria-hidden="true">
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
  const fitting = fittingDays(days, fittedOn);
  // The root font size: the box's rem, read as the chart draws. 18 if it cannot be read: the
  // site's base size (site.css --root-font-size, 112.5% of the browser's 16px).
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 18;
  // #668: room beside the first and last points for half their score, which is 1rem: 16px at
  // the base size, in rem so a score at 200% text is not cut by the chart's edge. Whole pixels:
  // the first and last points sit on the plot's edges, and a pointer on a point at a fractional
  // edge (a 16px root, as in the unit tests) can miss the plot and show no tooltip.
  const side = Math.round((16 / 18) * rem);

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
        <LineChart
          data={days}
          margin={{ top: fitting ? FITTING_TOP * rem : 24, right: side, bottom: 8, left: side }}
          accessibilityLayer={false}
        >
          {levels.map((level, i) => (
            <ReferenceArea
              key={level.code}
              y1={i === 0 ? 0 : bandEdge(i - 1)}
              y2={bandEdge(i)}
              fill={BAND_FILLS[level.color]?.[level.shade] ?? OTHER_BAND_FILL}
              fillOpacity={1}
              // A white line between bands, as between the score bar's segments.
              stroke="#fff"
              strokeWidth={2}
            />
          ))}
          {fitting && <FittingLine between={fitting} rem={rem} />}
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
