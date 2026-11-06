import { useState } from "react";

import AudiogramChart from "./AudiogramChart.jsx";
import { CHART, x, y } from "./audiogram.js";

const PRIMARY = "#1f4e8c";
const BANANA = "#fbeea8";
const CLIP = "speech-banana-clip";
// Each group's box, in chart units, by the groups' order: under the banana where there is room,
// over it for the two the row below cannot fit. The dot, not the box, is the real position.
// A tap picks the nearest centre, so every box's edges must be nearer its own centre than another's.
const BOX_CENTRES = [
  [80, 214],
  [146, 214],
  [208, 214],
  [219, 112],
  [272, 214],
  [279, 112],
];
const FONT_SIZE = 13;
const ROW_HEIGHT = 15;
const BOX_SIDE_ROOM = 8;
const BOX_FOOT_ROOM = 6;

const groupName = (group) => group.rows.join("");

function nearestGroup({ px, py }) {
  const distances = BOX_CENTRES.map(([cx, cy]) => Math.hypot(cx - px, cy - py));
  return distances.indexOf(Math.min(...distances));
}

function Banana({ outline }) {
  const edge = [...outline.top, ...outline.bottom];
  return (
    <>
      {/* The outline runs past 8000 Hz; what falls outside the chart is cropped. */}
      <clipPath id={CLIP}>
        <rect x={CHART.left} y={CHART.top} width={CHART.right - CHART.left} height={CHART.bottom - CHART.top} />
      </clipPath>
      <polygon
        className="speech-banana-area"
        points={edge.map(([frequency, db]) => `${x(frequency)},${y(db)}`).join(" ")}
        fill={BANANA}
        clipPath={`url(#${CLIP})`}
      />
    </>
  );
}

function GroupBox({ group, number, centre, selected }) {
  const [cx, cy] = centre;
  const width = Math.max(...group.rows.map((row) => row.length)) * FONT_SIZE + BOX_SIDE_ROOM;
  const height = group.rows.length * ROW_HEIGHT + BOX_FOOT_ROOM;
  const top = cy - height / 2;
  return (
    <g data-group={number} data-selected={selected}>
      <line x1={x(group.frequency)} y1={y(group.db)} x2={cx} y2={cy} stroke={PRIMARY} strokeWidth="1.2" />
      <circle cx={x(group.frequency)} cy={y(group.db)} r="3" fill={PRIMARY} />
      <rect
        x={cx - width / 2}
        y={top}
        width={width}
        height={height}
        rx="6"
        fill={selected ? PRIMARY : "#fff"}
        fillOpacity={selected ? 1 : 0.9}
        stroke={PRIMARY}
        strokeWidth="1.5"
      />
      {group.rows.map((row, i) => (
        <text
          key={row}
          x={cx}
          y={top + (i + 1) * ROW_HEIGHT}
          textAnchor="middle"
          fontSize={FONT_SIZE}
          fontWeight="700"
          fill={selected ? "#fff" : PRIMARY}
        >
          {row}
        </text>
      ))}
    </g>
  );
}

// Everything judged comes from the server (data.ears[].results); this only draws and picks.
export default function SpeechBananaApp({ data }) {
  const [selected, setSelected] = useState(null);
  const group = selected === null ? null : data.groups[selected];
  // The server lists the right ear first.
  const shown = data.ears[0];
  return (
    <>
      <div className="audiogram-chart">
        <AudiogramChart
          points={shown.marks}
          label={`聽力圖，畫出語言香蕉區、六群注音和${shown.label}的標記。要看每一群的結果，請用圖下的「用清單選」。`}
          behind={<Banana outline={data.banana} />}
          onTap={(at) => setSelected(nearestGroup(at))}
        >
          {data.groups.map((g, i) => (
            <GroupBox key={groupName(g)} group={g} number={i + 1} centre={BOX_CENTRES[i]} selected={i === selected} />
          ))}
        </AudiogramChart>
      </div>
      <div className="speech-banana-result" role="status">
        {group ? (
          <>
            <p className="speech-banana-result-title">{groupName(group)}</p>
            <p>{group.description}</p>
            <p>{group.examples}</p>
            {data.ears.map((ear) => (
              <p key={ear.ear}>
                <strong>{ear.label}：</strong>
                {ear.results[selected].text}
              </p>
            ))}
          </>
        ) : (
          <p>點圖上的注音，看那一群。</p>
        )}
      </div>
      <details className="dropdown-box mb-4">
        <summary>用清單選</summary>
        <div className="speech-banana-picks">
          {data.groups.map((g, i) => (
            <button
              key={groupName(g)}
              type="button"
              className="btn btn-outline-primary speech-banana-pick"
              aria-pressed={i === selected}
              onClick={() => setSelected(i)}
            >
              {groupName(g)}
            </button>
          ))}
        </div>
      </details>
    </>
  );
}
