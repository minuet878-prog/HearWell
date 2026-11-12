import { createRoot } from "react-dom/client";

import SpeechBananaApp from "./SpeechBananaApp.jsx";

// The page renders the data (json_script), judged on the server; this only draws it.
createRoot(document.getElementById("speech-banana")).render(
  <SpeechBananaApp data={JSON.parse(document.getElementById("speech-banana-data").textContent)} />,
);
