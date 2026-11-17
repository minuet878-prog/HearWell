import { createRoot } from "react-dom/client";

import TrendChart from "./TrendChart.jsx";

const container = document.getElementById("trend-plot");
// #650: data-fitted-on (YYYY/MM/DD) only when the current pair's fitting day is known.
if (container) {
  createRoot(container).render(
    <TrendChart code={container.dataset.questionnaire} fittedOn={container.dataset.fittedOn} />,
  );
}
