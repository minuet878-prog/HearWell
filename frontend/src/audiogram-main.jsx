import { createRoot } from "react-dom/client";

import AudiogramApp from "./AudiogramApp.jsx";

const container = document.getElementById("audiogram-app");
// Only the edit page has the saved audiogram.
const initial = document.getElementById("audiogram-initial");
if (container) {
  const saved = initial ? JSON.parse(initial.textContent) : null;
  createRoot(container).render(
    <AudiogramApp
      today={container.dataset.today}
      csrfToken={container.dataset.csrfToken}
      audiogramId={container.dataset.audiogramId}
      initialPoints={saved?.points}
      initialTestedOn={saved?.tested_on}
    />,
  );
}
