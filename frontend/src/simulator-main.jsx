import { createRoot } from "react-dom/client";

import SimulatorApp from "./SimulatorApp.jsx";
import { createEngine } from "./simulator-engine.js";

// The page renders the degrees and sentences (json_script, screening/simulator.py); this plays them.
createRoot(document.getElementById("simulator")).render(
  <SimulatorApp data={JSON.parse(document.getElementById("simulator-data").textContent)} engine={createEngine()} />,
);
