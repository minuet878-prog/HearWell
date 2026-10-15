import { createRoot } from "react-dom/client";

import TrendChart from "./TrendChart.jsx";

const container = document.getElementById("trend-chart");
if (container) createRoot(container).render(<TrendChart />);
