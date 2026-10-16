import { createRoot } from "react-dom/client";

import AudiogramChart from "./AudiogramChart.jsx";

// The page renders the points (json_script) and the interpretation; this only draws the chart.
const container = document.getElementById("audiogram-chart");
const data = document.getElementById("audiogram-points");
if (container && data) {
  createRoot(container).render(<AudiogramChart points={JSON.parse(data.textContent)} />);
}
