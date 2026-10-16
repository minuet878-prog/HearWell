import { createRoot } from "react-dom/client";

import AnswerApp from "./AnswerApp.jsx";

// The Django form stays until the questions have loaded, so a failed load still leaves a working page.
const container = document.getElementById("answer-app");
const fallback = document.getElementById("answer-form");
if (container && fallback) {
  createRoot(container).render(
    <AnswerApp
      questionnaireId={Number(container.dataset.questionnaireId)}
      userId={Number(container.dataset.userId)}
      csrfToken={fallback.querySelector("[name=csrfmiddlewaretoken]").value}
      onReady={() => {
        fallback.hidden = true;
      }}
    />,
  );
}
