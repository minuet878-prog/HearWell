import { createRoot } from "react-dom/client";

import AnswerApp from "./AnswerApp.jsx";

// The page's inline script hides the Django form before it is drawn (class answer-loading) and
// brings it back after 5 seconds. React takes over only while the page is still loading, so a
// failed or slow load leaves a working form (spec docs/specs/phase-05/phase5_answer_flash.md).
const container = document.getElementById("answer-app");
const fallback = document.getElementById("answer-form");
// The questionnaire's intro: React shows it per step (#153), so the page's copy goes once React is in.
const intro = document.getElementById("answer-intro");
const note = document.getElementById("answer-loading");
const page = document.documentElement.classList;

const showForm = () => {
  page.remove("answer-loading");
  if (note) note.textContent = "";
};

if (container && fallback) {
  const root = createRoot(container);
  root.render(
    <AnswerApp
      questionnaireId={Number(container.dataset.questionnaireId)}
      userId={Number(container.dataset.userId)}
      csrfToken={fallback.querySelector("[name=csrfmiddlewaretoken]").value}
      minutes={Number(container.dataset.minutes)}
      introHtml={intro.innerHTML}
      onReady={() => {
        // Too late: the form is back and may already have answers in it, so React stays out.
        if (!page.contains("answer-loading")) {
          root.unmount();
          return;
        }
        fallback.hidden = true;
        intro.hidden = true;
        showForm();
      }}
      onFail={showForm}
    />,
  );
}
