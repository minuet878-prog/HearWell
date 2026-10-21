import { useEffect, useRef, useState } from "react";

import { clearDraft, loadDraft, saveDraft } from "./draft.js";

// Same wording as the Django form (forms.HearingAidForm).
const HEARING_AID = {
  text: "這次填答時，您有沒有戴助聽器？",
  choices: [
    { value: true, label: "有戴" },
    { value: false, label: "沒戴" },
  ],
};
const FAILED = "送出失敗，請再按一次送出";

const newAnswers = () => ({ key: crypto.randomUUID(), wearing: null, answers: {}, step: 0 });
const hasAnything = (form) => form.wearing !== null || Object.keys(form.answers).length > 0;

// One page per question, step 0 being the hearing aid question. Each step is a history entry,
// so the browser back button is the previous question (spec 4.1). Scores come from the API only.
export default function AnswerApp({
  questionnaireId,
  userId,
  csrfToken,
  onReady,
  onFail = () => {},
  navigate = (url) => window.location.assign(url),
}) {
  const [questions, setQuestions] = useState(null);
  const [saved, setSaved] = useState(null);
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState({ type: "idle" });
  const moved = useRef(false);
  // Set once the answers were accepted (or already were, 409): nothing may save them again.
  const finished = useRef(false);
  const legend = useRef(null);

  // focus: only after the user chose to continue or start over, not on first load.
  // After a reload (or coming back from the result page) the browser still holds this page's entries
  // for steps 0..here, so reuse them instead of stacking more after them.
  function begin(start, focus) {
    const here = history.state?.answerStep;
    const from = Number.isInteger(here) ? here : 0;
    if (!Number.isInteger(here)) history.replaceState({ answerStep: 0 }, "");
    if (start.step < from) history.go(start.step - from);
    for (let step = from + 1; step <= start.step; step++) history.pushState({ answerStep: step }, "");
    moved.current = focus;
    setSaved(null);
    setForm(start);
  }

  useEffect(() => {
    fetch(`/api/questionnaires/${questionnaireId}/`, { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) throw new Error(`questionnaire ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const draft = loadDraft({ questionnaireId, userId, questionIds: data.questions.map((q) => q.id), allowNotApplicable: data.questions.some((q) => q.choices.some((c) => c.value === null)) });
        setQuestions(data.questions);
        if (draft) setSaved(draft);
        else begin(newAnswers(), false);
        onReady();
      })
      // Nothing is shown; the entry gives the page back to the Django form.
      .catch(() => onFail());
  }, []);

  useEffect(() => {
    const onPopState = (event) => {
      const step = event.state?.answerStep;
      if (!Number.isInteger(step)) return;
      moved.current = true;
      setForm((current) => current && { ...current, step });
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (form && hasAnything(form) && !finished.current) saveDraft({ ...form, userId, questionnaireId, savedAt: Date.now() });
  }, [form]);

  useEffect(() => {
    if (moved.current) legend.current?.focus();
    moved.current = false;
  }, [form?.step, form === null]);

  if (questions === null) return null;

  if (status.type === "duplicate") {
    return (
      <div className="answer-app">
        <p className="text-[calc(1.275rem+0.3vw)] min-[1200px]:text-[1.5rem] font-bold" role="alert">這份作答之前已經送出過</p>
        <a className="btn btn-primary btn-lg" href="/my_hearing">到我的紀錄看結果</a>
      </div>
    );
  }

  if (saved) {
    const where = saved.step === 0 ? "您上次還沒答完" : `您上次答到第 ${saved.step} 題`;
    return (
      <div className="answer-app">
        <h3 className="text-[calc(1.3rem+0.6vw)] min-[1200px]:text-[1.75rem]">{where}，要接著答嗎？</h3>
        <div className="answer-nav">
          <button type="button" className="btn btn-primary btn-lg" onClick={() => begin(saved, true)}>接著答</button>
          <button
            type="button"
            className="btn btn-outline-primary btn-lg"
            onClick={() => {
              clearDraft(questionnaireId);
              begin(newAnswers(), true);
            }}
          >
            重新開始
          </button>
        </div>
      </div>
    );
  }

  const { step } = form;
  const isHearingAid = step === 0;
  const question = isHearingAid ? HEARING_AID : questions[step - 1];
  const current = isHearingAid ? form.wearing : form.answers[question.id];
  const answered = current !== undefined && (!isHearingAid || current !== null);
  const isLast = step === questions.length;
  const isSending = status.type === "sending";

  function choose(value) {
    setStatus({ type: "idle" });
    setForm((f) => (isHearingAid ? { ...f, wearing: value } : { ...f, answers: { ...f.answers, [question.id]: value } }));
  }

  function goNext() {
    history.pushState({ answerStep: step + 1 }, "");
    moved.current = true;
    setForm((f) => ({ ...f, step: step + 1 }));
  }

  async function submit() {
    const missing = [
      form.wearing === null ? 0 : null,
      ...questions.map((q, i) => (form.answers[q.id] === undefined ? i + 1 : null)),
    ].filter((s) => s !== null);
    if (missing.length > 0) {
      setStatus({ type: "error", message: `還有 ${missing.length} 題沒有回答` });
      if (missing[0] !== step) history.go(missing[0] - step);
      return;
    }

    setStatus({ type: "sending" });
    let response = null;
    try {
      response = await fetch("/api/submissions/", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "Idempotency-Key": form.key,
        },
        body: JSON.stringify({
          questionnaire: questionnaireId,
          wearing_hearing_aid: form.wearing,
          answers: questions.map((q) => ({ question: q.id, score: form.answers[q.id] })),
        }),
      });
    } catch {
      // Network failure: the same receipt number is sent again next time.
    }

    if (response?.ok) {
      const { id } = await response.json();
      finished.current = true;
      clearDraft(questionnaireId);
      navigate(`/submission/${id}`);
      return;
    }
    if (response?.status === 400) {
      const body = await response.json().catch(() => ({}));
      const messages = Object.values(body).flat(Infinity).filter((m) => typeof m === "string");
      setStatus({ type: "error", message: `送出的資料有誤：${messages.join("、")}` });
    } else if (response?.status === 403) {
      setStatus({ type: "expired" });
    } else if (response?.status === 409) {
      finished.current = true;
      clearDraft(questionnaireId);
      setStatus({ type: "duplicate" });
    } else {
      setStatus({ type: "error", message: FAILED });
    }
  }

  const loginUrl = `/login?next=${encodeURIComponent(`/questionnaire/${questionnaireId}`)}`;

  return (
    <div className="answer-app">
      {/* The legend must be the fieldset's first child to name the radio group. */}
      <fieldset className="card card-body mb-4" disabled={isSending}>
        <legend ref={legend} tabIndex={-1} className="font-bold text-[calc(1.275rem+0.3vw)] min-[1200px]:text-[1.5rem]">
          {!isHearingAid && <span className="question-progress">第 {step} 題／共 {questions.length} 題</span>}
          {question.text}
        </legend>
        {!isHearingAid && question.scale ? (
          <div className="ssq-scale">
            <p className="text-[calc(1.3rem+0.6vw)] min-[1200px]:text-[1.75rem] font-bold" role="status">{current === undefined ? "未作答" : current === null ? "不適用" : `${current} 分`}</p>
            <label className="form-label" htmlFor={`ssq-score-${step}`}>選擇分數（0–10）</label>
            <input
              id={`ssq-score-${step}`} type="range" min="0" max="10" step="1"
              value={current ?? 5}
              aria-valuetext={current === undefined ? "未作答" : current === null ? "不適用" : `${current} 分`}
              onChange={(event) => choose(Number(event.target.value))}
              onPointerUp={(event) => choose(Number(event.currentTarget.value))}
            />
            <div className="flex justify-between gap-2 mb-4"><span>0：{question.scale.min_label}</span><span>10：{question.scale.max_label}</span></div>
            <div className="flex flex-wrap gap-2 mb-4">
              <button type="button" className="btn btn-outline-primary btn-lg" disabled={current === 0} onClick={() => choose(Math.max(0, (current ?? 5) - 1))}>減少 1 分</button>
              <button type="button" className="btn btn-outline-primary btn-lg" disabled={current === 10} onClick={() => choose(Math.min(10, (current ?? 5) + 1))}>增加 1 分</button>
            </div>
            <label><input type="radio" name={`answer-step-${step}`} checked={current === null} onChange={() => choose(null)} /> 不適用</label>
          </div>
        ) : <div className="choice-group">
          {question.choices.map((choice) => (
            <label key={String(choice.value)}>
              <input
                type="radio"
                name={`answer-step-${step}`}
                checked={current === choice.value}
                onChange={() => choose(choice.value)}
              />
              {choice.label}
            </label>
          ))}
        </div>}
      </fieldset>

      {status.type === "error" && <p className="text-xl/normal font-bold text-danger" role="alert">{status.message}</p>}
      {status.type === "expired" && (
        <div role="alert" className="mb-4">
          <p className="text-xl/normal font-bold text-danger">登入已經過期，請重新登入</p>
          <a className="btn btn-primary btn-lg" href={loginUrl}>登入</a>
        </div>
      )}

      <div className="answer-nav">
        {!isHearingAid && (
          <button
            type="button"
            className="btn btn-outline-primary btn-lg"
            disabled={isSending}
            onClick={() => history.back()}
          >
            上一題
          </button>
        )}
        {isLast ? (
          <button type="button" className="btn btn-primary btn-lg" disabled={!answered || isSending} onClick={submit}>
            {isSending ? "送出中…" : "送出"}
          </button>
        ) : (
          <button type="button" className="btn btn-primary btn-lg" disabled={!answered} onClick={goNext}>
            下一題
          </button>
        )}
      </div>
    </div>
  );
}
