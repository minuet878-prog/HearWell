import { useState } from "react";

import AudiogramChart from "./AudiogramChart.jsx";
import { CHART, DB_MIN, x, y } from "./audiogram.js";

const PRIMARY = "#1f4e8c";
const BANANA = "#fbeea8";
const CLIP = "speech-banana-clip";
const HATCH = "speech-banana-hatch";
const HATCH_CLIP = "speech-banana-hatch-clip";
// Each group's box, in chart units, by the groups' order: under the banana where there is room,
// over it for the two the row below cannot fit. The dot, not the box, is the real position.
const BOX_CENTRES = [
  [80, 214],
  [146, 214],
  [208, 214],
  [222, 112],
  [272, 214],
  [279, 112],
];
const FONT_SIZE = 13;
const ROW_HEIGHT = 15;
const BOX_SIDE_ROOM = 8;
const BOX_FOOT_ROOM = 6;

const groupName = (group) => group.rows.join("");
const chartPoint = ([frequency, db]) => `${x(frequency)},${y(db)}`;

function Banana({ outline, stretches }) {
  const edge = [...outline.top, ...outline.bottom].map(chartPoint).join(" ");
  return (
    <>
      {/* The outline runs past 8000 Hz; what falls outside the chart is cropped. */}
      <clipPath id={CLIP}>
        <rect x={CHART.left} y={CHART.top} width={CHART.right - CHART.left} height={CHART.bottom - CHART.top} />
      </clipPath>
      <clipPath id={HATCH_CLIP}>
        <polygon points={edge} />
      </clipPath>
      <pattern id={HATCH} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="3.5" y1="0" x2="3.5" y2="7" stroke="#5a6371" strokeWidth="1.2" />
      </pattern>
      <polygon className="speech-banana-area" points={edge} fill={BANANA} clipPath={`url(#${CLIP})`} />
      {/* Each stretch hatches what is over its line (softer than it); the banana keeps only its own part. */}
      {stretches.map((stretch) => (
        <polygon
          key={stretch[0][0]}
          className="speech-banana-hatch"
          points={[[stretch[0][0], DB_MIN], ...stretch, [stretch.at(-1)[0], DB_MIN]].map(chartPoint).join(" ")}
          fill={`url(#${HATCH})`}
          clipPath={`url(#${HATCH_CLIP})`}
        />
      ))}
    </>
  );
}

function GroupBox({ group, number, centre, selected, hard }) {
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
        strokeDasharray={hard ? "4 3" : undefined}
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

// Under the marks, over the boxes: the left ear's blue is the colour of a picked box, so a white
// edge keeps its marks and line in sight there.
function MarkEdges({ ear }) {
  return (
    <g className="speech-banana-mark-edges">
      {ear.stretches.map((stretch) => (
        <polyline key={stretch[0][0]} points={stretch.map(chartPoint).join(" ")} fill="none" stroke="#fff" strokeWidth="3.5" />
      ))}
      {ear.marks.map((mark) => (
        <circle key={mark.frequency} cx={x(mark.frequency)} cy={y(mark.db)} r="8" fill="#fff" />
      ))}
    </g>
  );
}

// Everything judged comes from the server (data.ears[].results); this only draws and picks.
export default function SpeechBananaApp({ data }) {
  const [selected, setSelected] = useState(null);
  const group = selected === null ? null : data.groups[selected];
  // The server lists the right ear first.
  const [shownEar, setShownEar] = useState(0);
  const shown = data.ears[shownEar];
  return (
    <>
      <div className="ear-switch" role="group" aria-label="選耳朵">
        {data.ears.map((ear, i) => (
          <button key={ear.ear} type="button" aria-pressed={i === shownEar} onClick={() => setShownEar(i)}>
            {ear.label}
          </button>
        ))}
      </div>
      <div className="audiogram-chart">
        <AudiogramChart
          points={shown.marks}
          label={`聽力圖，畫出語言香蕉區、六群注音和${shown.label}的標記。要看每一群的結果，請用圖下的「用清單選」。`}
          behind={
            <>
              <Banana outline={data.banana} stretches={shown.stretches} />
              {data.groups.map((g, i) => (
                <GroupBox
                  key={groupName(g)}
                  group={g}
                  number={i + 1}
                  centre={BOX_CENTRES[i]}
                  selected={i === selected}
                  hard={shown.results[i].status === "hard"}
                />
              ))}
              <MarkEdges ear={shown} />
            </>
          }
        />
      </div>
      <p className="mb-4">黃色是語言香蕉區，是說話聲通常落在的範圍。斜線蓋住的部分和虛線框的注音，這一耳沒戴助聽器時可能不容易聽到。</p>
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
