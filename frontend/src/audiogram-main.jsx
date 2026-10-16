import { createRoot } from "react-dom/client";

import AudiogramApp from "./AudiogramApp.jsx";

const container = document.getElementById("audiogram-app");
if (container) {
  createRoot(container).render(
    <AudiogramApp today={container.dataset.today} csrfToken={container.dataset.csrfToken} />,
  );
}
