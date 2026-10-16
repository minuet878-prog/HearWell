import { createRoot } from "react-dom/client";

import AudiogramChart from "./AudiogramChart.jsx";

// The page renders the points (json_script) and the interpretation; this only draws the chart.
// The compare page adds the older audiogram's points.
const container = document.getElementById("audiogram-chart");
const data = document.getElementById("audiogram-points");
const old = document.getElementById("audiogram-old-points");
if (container && data) {
  createRoot(container).render(
    <AudiogramChart points={JSON.parse(data.textContent)} oldPoints={old ? JSON.parse(old.textContent) : undefined} />,
  );
}
