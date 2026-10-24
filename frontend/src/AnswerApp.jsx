import { useEffect, useRef, useState } from "react";

import { clearDraft, loadDraft, saveDraft } from "./draft.js";

// Same choices as the Django form (forms.HearingAidForm); the question itself is the
// questionnaire's own (the API's wearing_question, #212).
const HEARING_AID_CHOICES = [
  { value: true, label: "有戴" },
  { value: false, label: "沒戴" },
];
const FAILED = "送出失敗，請再按一次送出";
// #326 B4: how long ✓ 已儲存 stays beside the progress.
const SAVED_FOR_MS = 1500;

// #326 A6: the shape says which way each button goes; decoration only, so the name stays the words.
function NavIcon({ d }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d={d} /></svg>
  );
}
const ARROW_LEFT = "M19 12H5M11 6l-6 6 6 6";
const ARROW_RIGHT = "M5 12h14M13 6l6 6-6 6";
const TICK = "M5 12.5l4.5 4.5L19 7";

// One page per question, step 0 being the hearing aid question. Each step is a history entry,
// so the browser back button is the previous question (spec 4.1). Scores come from the API only.
export default function AnswerApp({
  questionnaireId,
  userId,
  csrfToken,
  minutes,
  introHtml,
  preselectUnaided = false,
  // Why 沒戴 is already chosen when catching up an unaided record (#154); from screening.html.
  unaidedHint,
  // Answered wearing hearing aids by definition (#170, e.g. SADL): no wearing step at all.
  alwaysAided = false,
  // IOI-HA (#245): no wearing step, and none sent; the record stays 未記錄 as on the web form.
  skipWearing = false,
  // IOI-HA's signed norm basis from the page (ADR 0002), sent back with the answers.
  normToken,
  onReady,
  onFail = () => {},
  navigate = (url) => window.location.assign(url),
}) {
  const [questions, setQuestions] = useState(null);
  const [wearingQuestion, setWearingQuestion] = useState(null);
  const [saved, setSaved] = useState(null);
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState({ type: "idle" });
  const [introOpen, setIntroOpen] = useState(false);
  // #326 C5: 下一題 or 送出 pressed with nothing chosen on this question.
  const [chooseFirst, setChooseFirst] = useState(false);
  // #326 B4: ✓ 已儲存 shows while this is above 0; a new number restarts it.
  const [savedFlash, setSavedFlash] = useState(0);
  const savedTimer = useRef(null);
  // #326 C3: the question whose segment a choice just turned from unanswered to answered.
  const [justFilled, setJustFilled] = useState(null);
  // #326 C4: the user has moved to another question, so each question shown from now fades in.
  const [turned, setTurned] = useState(false);
  // The form changed because the user chose an answer (not by moving to another question).
  const chose = useRef(false);
  const moved = useRef(false);
  // Set once the answers were accepted (or already were, 409): nothing may save them again.
  const finished = useRef(false);
  const legend = useRef(null);
  // Only where a fresh start begins: a draft keeps the user's own choice, and the preselection
  // by itself is nothing to keep, so opening the page and leaving asks nothing next time.
  const startWearing = alwaysAided ? true : preselectUnaided ? false : null;
  const asksWearing = !alwaysAided && !skipWearing;
  const newAnswers = () => ({
    key: crypto.randomUUID(),
    wearing: startWearing,
    answers: {},
    step: asksWearing ? 0 : 1,
  });
  const hasAnything = (form) => form.wearing !== startWearing || Object.keys(form.answers).length > 0;
  // The first step shown: the hearing aid question, or question 1 when there is none (#170).
  const groundFloor = asksWearing ? 0 : 1;

  // focus: only after the user chose to continue or start over, not on first load.
  // After a reload (or coming back from the result page) the browser still holds this page's entries
  // for steps groundFloor..here, so reuse them instead of stacking more after them.
  function begin(start, focus) {
    const here = history.state?.answerStep;
    const from = Number.isInteger(here) ? here : groundFloor;
    if (!Number.isInteger(here)) history.replaceState({ answerStep: groundFloor }, "");
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
        setWearingQuestion(data.wearing_question);
        setQuestions(data.questions);
        if (draft) setSaved(draft);
        else begin(newAnswers(), false);
        onReady();
      })
      // Nothing is shown; the entry gives the page back to the Django form.
      .catch(() => onFail());
  }, []);

  // Feedback on this question's choice goes when the user moves to another question, so it never
  // plays again there.
  function leaveQuestion() {
    clearTimeout(savedTimer.current);
    setSavedFlash(0);
    setJustFilled(null);
    setTurned(true);
  }

  useEffect(() => {
    const onPopState = (event) => {
      const step = event.state?.answerStep;
      if (!Number.isInteger(step)) return;
      moved.current = true;
      setChooseFirst(false);
      leaveQuestion();
      setForm((current) => current && { ...current, step });
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const kept = form && hasAnything(form) && !finished.current && saveDraft({ ...form, userId, questionnaireId, savedAt: Date.now() });
    if (kept && chose.current) {
      clearTimeout(savedTimer.current);
      setSavedFlash((n) => n + 1);
      savedTimer.current = setTimeout(() => setSavedFlash(0), SAVED_FOR_MS);
    }
    chose.current = false;
  }, [form]);

  useEffect(() => () => clearTimeout(savedTimer.current), []);

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
        <h3 className="heading-bar text-[calc(1.3rem+0.6vw)] min-[1200px]:text-[1.75rem]">{where}，要接著答嗎？</h3>
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
  const isHearingAid = asksWearing && step === 0;
  // IOI-HA has no wearing step, so its intro, which tells the norm basis before answering
  // (ADR 0002), is in full on item 1 instead.
  const introInFull = isHearingAid || (skipWearing && step === 1);
  const question = isHearingAid ? { text: wearingQuestion, choices: HEARING_AID_CHOICES } : questions[step - 1];
  const current = isHearingAid ? form.wearing : form.answers[question.id];
  const answered = current !== undefined && (!isHearingAid || current !== null);
  // Only while 沒戴 is chosen: after switching to 有戴 the hint would contradict it (site owner, 1.B).
  const showHint = isHearingAid && preselectUnaided && form.wearing === false;
  const isLast = step === questions.length;
  const isSending = status.type === "sending";
  // The questionnaire's minutes shared out over this question and the ones after it, at least 1.
  const minutesLeft = Math.max(1, Math.round((minutes * (questions.length - step + 1)) / questions.length));

  function choose(value) {
    setStatus({ type: "idle" });
    setChooseFirst(false);
    chose.current = true;
    if (!isHearingAid && current === undefined) setJustFilled(question.id);
    setForm((f) => (isHearingAid ? { ...f, wearing: value } : { ...f, answers: { ...f.answers, [question.id]: value } }));
  }

  // Not disabled until answered (#326 C5): pressing says what is missing and goes back to the question.
  function askForAChoice() {
    setChooseFirst(true);
    legend.current.focus();
  }

  function goNext() {
    if (!answered) return askForAChoice();
    history.pushState({ answerStep: step + 1 }, "");
    moved.current = true;
    leaveQuestion();
    setForm((f) => ({ ...f, step: step + 1 }));
  }

  async function submit() {
    if (!answered) return askForAChoice();
    const missing = [
      asksWearing && form.wearing === null ? 0 : null,
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
          ...(skipWearing ? {} : { wearing_hearing_aid: form.wearing }),
          ...(normToken ? { norm_token: normToken } : {}),
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
      {/* The page's own intro (the definition's intro_template), in full only on the first page. */}
      {introInFull ? (
        <div dangerouslySetInnerHTML={{ __html: introHtml }} />
      ) : (
        <div className="answer-about mb-4">
          <button
            type="button"
            aria-expanded={introOpen}
            aria-controls="answer-intro-text"
            onClick={() => setIntroOpen((open) => !open)}
          >
            這份問卷在問什麼？
          </button>
          <div id="answer-intro-text">{introOpen && <div dangerouslySetInnerHTML={{ __html: introHtml }} />}</div>
        </div>
      )}
      {/* The legend must be the fieldset's first child to name the radio group. A flat block: only
          the choices are white (ADR 0022). */}
      <fieldset
        className="mb-4"
        disabled={isSending}
        aria-describedby={showHint ? "answer-hearing-aid-hint" : undefined}
      >
        <legend ref={legend} tabIndex={-1} className="font-bold text-[calc(1.275rem+0.3vw)] min-[1200px]:text-[1.5rem]">
          {!isHearingAid && (
            <>
              {/* The register steps' bar (#151), one segment per question answered or not; only the
                  colour changes, the segment a choice just answered filling once (ADR 0028). The
                  text says it all. */}
              <span className="step-progress-bar mb-2" aria-hidden="true">
                {questions.map((q) => (
                  <span
                    key={q.id}
                    className={form.answers[q.id] === undefined ? "step-progress-segment" : q.id === justFilled ? "step-progress-segment is-done is-filling" : "step-progress-segment is-done"}
                  />
                ))}
              </span>
              {/* #326 B4: the flash keeps its room when empty, so showing it moves nothing; not read
                  aloud on every answer (the footer note says it once). */}
              <span className="question-progress-line">
                <span className="question-progress">第 {step} 題／共 {questions.length} 題・還剩大約 {minutesLeft} 分鐘</span>
                <span className="answer-saved" aria-hidden="true">
                  {savedFlash > 0 && <span key={savedFlash}>✓ 已儲存</span>}
                </span>
              </span>
            </>
          )}
          {/* Remounted on each question, so the fade plays once per question shown. */}
          <span key={step} className={turned ? "is-fading-in" : undefined}>{question.text}</span>
        </legend>
        {/* Its own id: the hidden Django form keeps #hearing-aid-hint. */}
        {showHint && <p id="answer-hearing-aid-hint">{unaidedHint}</p>}
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
        {step > groundFloor && (
          <button
            type="button"
            className="btn btn-outline-primary btn-lg"
            disabled={isSending}
            onClick={() => history.back()}
          >
            <NavIcon d={ARROW_LEFT} />
            上一題
          </button>
        )}
        {isLast ? (
          <button type="button" className="btn btn-primary btn-lg" disabled={isSending} onClick={submit}>
            {isSending ? (
              <>
                <span className="spinner" aria-hidden="true" />
                送出中…
              </>
            ) : (
              <>
                <NavIcon d={TICK} />
                送出
              </>
            )}
          </button>
        ) : (
          <button type="button" className="btn btn-primary btn-lg" disabled={isSending} onClick={goNext}>
            下一題
            <NavIcon d={ARROW_RIGHT} />
          </button>
        )}
      </div>
      {chooseFirst && <p className="mt-4 text-xl/normal font-bold text-danger" role="alert">請先選一個答案</p>}
      {/* Shortened by the site owner (answer page tidy-up); draft.js keeps it in this browser only. */}
      <p className="answer-autosave">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 4h11l3 3v13H5z" /><path d="M8 4v5h7V4M8 20v-6h8v6" /></svg>
        答案會自動存在這支手機，中途離開也沒關係。
      </p>
    </div>
  );
}
