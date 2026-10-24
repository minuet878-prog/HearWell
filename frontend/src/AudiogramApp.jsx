import { useEffect, useRef, useState } from "react";

import AudiogramChart from "./AudiogramChart.jsx";
import { DB_MAX, DB_MIN, SYMBOLS, frequenciesFor, place, pointKey } from "./audiogram.js";

const FAILED = "存檔失敗，請再按一次存檔";
// DRF nests a list item's errors by index ({points: {0: {...}}}), so collect strings at any depth.
const texts = (value) => (typeof value === "string" ? [value] : Object.values(value ?? {}).flatMap(texts));
const NO_RESPONSE = "nr";
// #199, #200 (spec #183 stories 80-93): one thing per step on one screen; only saving checks.
const STEPS = ["檢查日期", "標右耳", "標左耳", "確認存檔"];
const STEP_EAR = { 2: "right", 3: "left" };
const EAR_STEP = { right: 2, left: 3 };
const EAR_LABEL = { right: "右耳", left: "左耳" };
const FORWARD = { 1: "下一步：標右耳", 2: "右耳標完了，換左耳", 3: "左耳標完了，確認存檔" };

// "氣導 n 個、骨導 n 個" for one ear, with no total: a report rarely tests every frequency.
function earCount(points, ear) {
  const marked = Object.values(points).filter((p) => p.ear === ear);
  const count = (conduction) => marked.filter((p) => p.conduction === conduction).length;
  return `氣導 ${count("air")} 個、骨導 ${count("bone")} 個`;
}
const hasMarks = (points, ear) => Object.values(points).some((p) => p.ear === ear);

function levelOptions(conduction) {
  const values = [];
  for (let db = DB_MIN; db <= DB_MAX[conduction]; db += 5) values.push(db);
  return values;
}

// The keyboard and screen-reader way in (spec 3): one select and one masking box per frequency,
// in sync with the chart.
function ValueTable({ points, symbols, onSet, onMask }) {
  return (
    <details className="audiogram-table dropdown-box mb-4">
      <summary>用數值輸入（鍵盤或螢幕閱讀器）</summary>
      {symbols.map((symbol) => (
        <fieldset key={symbol.key} className="mt-2">
          <legend className="text-xl/normal font-bold">{symbol.label}</legend>
          <div className="audiogram-table-grid">
            {frequenciesFor(symbol.conduction).map((frequency) => {
              const point = points[pointKey(symbol.ear, symbol.conduction, frequency)];
              const value = point ? (point.no_response ? NO_RESPONSE : String(point.db)) : "";
              const id = `value-${symbol.key}-${frequency}`;
              const name = `${symbol.label} ${frequency} Hz`;
              return (
                <div key={frequency}>
                  <label htmlFor={id} className="visually-hidden">{name}</label>
                  <span aria-hidden="true">{frequency} Hz</span>
                  <select id={id} className="form-select" value={value} onChange={(e) => onSet(symbol, frequency, e.target.value)}>
                    <option value="">未標記</option>
                    {levelOptions(symbol.conduction).map((db) => (
                      <option key={db} value={db}>{`${db} dB`}</option>
                    ))}
                    <option value={NO_RESPONSE}>無反應</option>
                  </select>
                  <label className="form-check">
                    <input
                      type="checkbox"
                      className="form-check-input"
                      aria-label={`${name} 遮蔽`}
                      checked={Boolean(point?.masked)}
                      disabled={!point}
                      onChange={(e) => onMask(symbol, frequency, e.target.checked)}
                    />
                    <span aria-hidden="true">遮蔽</span>
                  </label>
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
    </details>
  );
}

// With audiogramId it edits a saved audiogram (spec phase5_audiogram_2.md 4.1): it opens with the
// saved points and date, and saving replaces the whole audiogram.
export default function AudiogramApp({
  today,
  csrfToken,
  audiogramId,
  initialPoints = [],
  initialTestedOn = "",
  navigate = (url) => window.location.assign(url),
}) {
  const [step, setStep] = useState(1);
  const [symbolKey, setSymbolKey] = useState("right-air");
  // Stays as set until switched off (spec question 18).
  const [masked, setMasked] = useState(false);
  const [points, setPoints] = useState(() =>
    Object.fromEntries(initialPoints.map((p) => [pointKey(p.ear, p.conduction, p.frequency), p])),
  );
  const [last, setLast] = useState(null);
  const [testedOn, setTestedOn] = useState(initialTestedOn);
  const [errors, setErrors] = useState([]);
  const [sending, setSending] = useState(false);
  // One receipt number per page, so a retry after a lost response cannot save twice. Editing needs
  // none: putting the same audiogram again changes nothing.
  const key = useRef(crypto.randomUUID());
  const busy = useRef(false);

  const symbol = SYMBOLS.find((s) => s.key === symbolKey);
  const ear = STEP_EAR[step];
  const earSymbols = SYMBOLS.filter((s) => s.ear === ear);
  // Focus follows the step the user opens (65+ SPA risk), never on first load.
  const stepText = useRef(null);
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current) stepText.current?.focus();
  }, [step]);

  const goTo = (next) => {
    moved.current = true;
    setErrors([]);
    setLast(null);
    if (STEP_EAR[next]) setSymbolKey(`${STEP_EAR[next]}-air`);
    setStep(next);
  };

  const commit = (target, frequency, level, mark = masked) => {
    const next = place(points, target, frequency, level, mark);
    const changed = pointKey(target.ear, target.conduction, frequency);
    setPoints(next);
    if (next[changed]) setLast(changed);
    else if (last === changed) setLast(null);
  };

  const setFromTable = (target, frequency, value) => {
    const changed = pointKey(target.ear, target.conduction, frequency);
    if (value === "") {
      const { [changed]: _removed, ...others } = points;
      setPoints(others);
      if (last === changed) setLast(null);
      return;
    }
    // A select only fires on a new value, so place() never takes this as "same point, delete".
    const level = value === NO_RESPONSE ? { db: DB_MAX[target.conduction], noResponse: true } : { db: Number(value), noResponse: false };
    commit(target, frequency, level, points[changed]?.masked ?? masked);
  };

  const maskFromTable = (target, frequency, checked) => {
    const point = points[pointKey(target.ear, target.conduction, frequency)];
    commit(target, frequency, { db: point.db, noResponse: point.no_response }, checked);
  };

  const clearLast = () => {
    const { [last]: _removed, ...others } = points;
    setPoints(others);
    setLast(null);
  };

  async function save() {
    if (busy.current) return;
    const problems = [];
    if (Object.keys(points).length === 0) problems.push("請至少標記一個點");
    if (!testedOn) problems.push("請填寫檢查日期");
    else if (testedOn > today) problems.push("檢查日期不能是未來");
    setErrors(problems);
    if (problems.length > 0) return;

    busy.current = true;
    setSending(true);
    let response = null;
    const editing = audiogramId != null;
    const headers = { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": csrfToken };
    if (!editing) headers["Idempotency-Key"] = key.current;
    try {
      response = await fetch(editing ? `/api/audiograms/${audiogramId}/` : "/api/audiograms/", {
        method: editing ? "PUT" : "POST",
        headers,
        body: JSON.stringify({ tested_on: testedOn, points: Object.values(points) }),
      });
    } catch {
      // Network failure: the next attempt sends the same receipt number.
    }
    if (response?.ok) {
      const { id } = await response.json();
      navigate(`/audiograms/${id}`);
      return;
    }
    busy.current = false;
    setSending(false);
    if (response?.status === 400) {
      const body = await response.json().catch(() => ({}));
      setErrors(texts(body));
    } else if (response?.status === 403) {
      setErrors(["登入已經過期，請重新登入後再存檔"]);
    } else if (response?.status === 404) {
      setErrors(["這張聽力圖已經不存在，請到聽力圖清單查看"]);
    } else if (response?.status === 409) {
      setErrors(["這張聽力圖已經存過了，請到聽力圖清單查看"]);
    } else {
      setErrors([FAILED]);
    }
  }

  const lastPoint = last && points[last];
  const lastLabel = lastPoint && `${SYMBOLS.find((s) => s.ear === lastPoint.ear && s.conduction === lastPoint.conduction).label} ${lastPoint.frequency} Hz`;

  const errorList = errors.length > 0 && (
    <div role="alert" className="alert alert-danger">
      {errors.map((message) => (
        <p key={message} className="mb-0">{message}</p>
      ))}
    </div>
  );

  return (
    <div className="audiogram-app">
      <div className="step-progress">
        <p ref={stepText} tabIndex={-1} className="step-progress-text">
          第 {step} 步／共 {STEPS.length} 步：{STEPS[step - 1]}
        </p>
        <div className="step-progress-bar" aria-hidden="true">
          {STEPS.map((name, i) => (
            <span key={name} className={i < step ? "step-progress-segment is-done" : "step-progress-segment"} />
          ))}
        </div>
      </div>

      {step === 1 && (
        <div className="mb-4">
          <label htmlFor="tested-on" className="form-label text-xl/normal font-bold">檢查日期</label>
          <input id="tested-on" type="date" className="form-control form-control-lg" max={today} value={testedOn} onChange={(e) => setTestedOn(e.target.value)} />
        </div>
      )}

      {ear && (
        <>
          {/* Editing (pages tidy-up): said on the ear steps, where the saved marks are in sight. */}
          {audiogramId != null && <p className="tip-box">原本標的點已經放在圖上，照報告移動、刪除或補上，再按存檔。</p>}
          <section className="mb-4">
            <p className="font-bold">報告上的 O 是右耳（通常是紅色），X 是左耳（通常是藍色）</p>
            <ol className="audiogram-howto">
              <li>選下面的符號</li>
              <li>在圖上按住，上下拖到報告上的位置</li>
              <li>放開就標好了；標錯再點一下可以刪除</li>
            </ol>
            <p className="text-base mb-0">報告上符號下面有箭頭（無反應），就往下拖出圖外。</p>
          </section>
          <div className="audiogram-symbols" role="group" aria-label="要標記的符號">
            {earSymbols.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`btn audiogram-symbol ear-${s.ear}`}
                aria-pressed={s.key === symbolKey}
                onClick={() => setSymbolKey(s.key)}
              >
                {s.label} <span aria-hidden="true">{masked ? s.maskedMark : s.mark}</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            className={`btn btn-lg w-full mb-2 audiogram-mask-switch${masked ? " on" : ""}`}
            aria-pressed={masked}
            onClick={() => setMasked(!masked)}
          >
            {masked ? "遮蔽：開（△ □ [ ]）" : "遮蔽：關"}
          </button>
          {/* The dashed frame keeps masking in sight while the eyes are on the chart. */}
          <div className={`audiogram-chart${masked ? " masking" : ""}`}>
            <AudiogramChart points={Object.values(points)} symbol={symbol} masked={masked} onCommit={(f, level) => commit(symbol, f, level)} />
          </div>
          <p className="audiogram-count font-bold mb-2">
            {EAR_LABEL[ear]}已標：{earCount(points, ear)}
          </p>
          <button type="button" className="btn btn-outline-secondary btn-lg w-full mb-4" disabled={!lastPoint} onClick={clearLast}>
            {lastPoint ? `清除 ${lastLabel}` : "清除剛標的點"}
          </button>
          <ValueTable points={points} symbols={earSymbols} onSet={setFromTable} onMask={maskFromTable} />
        </>
      )}

      {step === 4 && (
        <>
          <p className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-bold">檢查日期：{testedOn ? testedOn.replaceAll("-", "/") : "未填"}</span>
            <button type="button" className="btn btn-link" onClick={() => goTo(1)}>改日期</button>
          </p>
          {/* Both ears, read only: nothing to mark with and no reading before saving. */}
          <div className="audiogram-chart">
            <AudiogramChart points={Object.values(points)} />
          </div>
          {["right", "left"].map((side) => (
            <p key={side} className="flex flex-wrap items-center justify-between gap-2">
              <span>{`${EAR_LABEL[side]}：${hasMarks(points, side) ? earCount(points, side) : "還沒有標任何點"}`}</span>
              <button type="button" className="btn btn-link" onClick={() => goTo(EAR_STEP[side])}>{`改${EAR_LABEL[side]}`}</button>
            </p>
          ))}
          <ValueTable points={points} symbols={SYMBOLS} onSet={setFromTable} onMask={maskFromTable} />
          {errorList}
          <button type="button" className="btn btn-primary btn-lg w-full" disabled={sending} onClick={save}>
            {sending ? (
              <>
                <span className="spinner" aria-hidden="true" />
                存檔中…
              </>
            ) : (
              "存檔"
            )}
          </button>
        </>
      )}

      {step < 4 && (
        <button type="button" className="btn btn-primary btn-lg w-full mb-2" onClick={() => goTo(step + 1)}>
          {FORWARD[step]}
        </button>
      )}
      {step > 1 && (
        <button type="button" className="btn btn-outline-primary btn-lg w-full" onClick={() => goTo(step - 1)}>
          上一步
        </button>
      )}
    </div>
  );
}
