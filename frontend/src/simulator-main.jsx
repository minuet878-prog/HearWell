import { createRoot } from "react-dom/client";

import SimulatorApp from "./SimulatorApp.jsx";
import { createEngine } from "./simulator-engine.js";

// The page renders the degrees and sentences (json_script, screening/simulator.py); this plays them.
const data = JSON.parse(document.getElementById("simulator-data").textContent);
createRoot(document.getElementById("simulator")).render(
  <SimulatorApp data={data} engine={createEngine(data.frequencies)} />,
);
