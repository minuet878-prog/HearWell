import { createRoot } from "react-dom/client";

import TrendChart from "./TrendChart.jsx";

const container = document.getElementById("trend-plot");
if (container) createRoot(container).render(<TrendChart code={container.dataset.questionnaire} />);
