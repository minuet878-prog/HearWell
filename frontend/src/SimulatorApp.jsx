import { useEffect, useId, useMemo, useState } from "react";

import { BLOCKS, meterBlocks } from "./simulator.js";

// #487 (spec #484, the #485 mockup E1 + V1, ADR 0053): pick a typical degree, play one sentence
// at a time, switch 模擬｜正常聽 while it plays. engine does the sound (simulator-engine.js; a
// fake in tests): play(url, onEnded), stop(), setCurve(thresholds), 正常聽 being all zeros, and
// setBackground(url), null for 安靜 (#488).
export default function SimulatorApp({ data, engine }) {
  const [levelIndex, setLevelIndex] = useState(0);
  const [normal, setNormal] = useState(false);
  const [sentenceIndex, setSentenceIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [restaurant, setRestaurant] = useState(false);
  const saidId = useId();

  const level = data.levels[levelIndex];
  const sentence = data.sentences[sentenceIndex];
  const thresholds = useMemo(
    () => (normal ? data.frequencies.map(() => 0) : level.thresholds),
    [normal, data.frequencies, level],
  );

  // A new degree or 正常聽 changes the curve only: whatever plays goes on playing.
  useEffect(() => {
    engine.setCurve(thresholds);
  }, [engine, thresholds]);

  // The restaurant goes under the speech, or away, without stopping it either (#488).
  useEffect(() => {
    engine.setBackground(restaurant ? data.restaurant.audio : null);
  }, [engine, restaurant, data.restaurant.audio]);

  function play(index) {
    setPlaying(true);
    engine.play(data.sentences[index].audio, () => setPlaying(false));
  }

  function pickLevel(index) {
    setLevelIndex(index);
    setNormal(false);
  }

  function step(by) {
    const count = data.sentences.length;
    const next = (sentenceIndex + by + count) % count;
    setSentenceIndex(next);
    setRevealed(false);
    if (playing) {
      engine.stop();
      play(next);
    }
  }

  function togglePlay() {
    if (playing) {
      engine.stop();
      setPlaying(false);
    } else {
      play(sentenceIndex);
    }
  }

  return (
    <>
      <div className="simulator-chips" role="group" aria-label="程度">
        {data.levels.map((item, i) => (
          <button key={item.code} type="button" className="simulator-chip" aria-pressed={i === levelIndex} onClick={() => pickLevel(i)}>
            {item.name}
          </button>
        ))}
      </div>
      <section className="simulator-player" aria-label="播放">
        <div className="simulator-meter">
          <p className="simulator-line" aria-live="polite">
            <b>{normal ? "正常聽" : level.name}</b>：{normal ? data.normal : level.line}
          </p>
          <div className="simulator-bars" aria-hidden="true">
            {meterBlocks(thresholds).map((count, band) => (
              <span key={data.frequencies[band]} className="simulator-bar">
                {Array.from({ length: BLOCKS }, (_, block) => (
                  <span key={block} className={block < count ? "is-lit" : undefined} />
                ))}
              </span>
            ))}
          </div>
          <p className="simulator-ends" aria-hidden="true">
            <span>低沉<span className="simulator-zhuyin">ㄇㄅㄨ</span></span>
            <span>尖細<span className="simulator-zhuyin">ㄙㄒㄘ</span></span>
          </p>
        </div>
        <div className="simulator-controls">
          <button type="button" className="simulator-step" aria-label="上一句" onClick={() => step(-1)}>
            <span aria-hidden="true">‹</span>
          </button>
          <button type="button" className="simulator-play" aria-label={playing ? "暫停" : "播放"} onClick={togglePlay}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              {playing ? <path d="M6 4.5h4.2v15H6zM13.8 4.5H18v15h-4.2z" /> : <path d="M7 4.5v15l13-7.5z" />}
            </svg>
          </button>
          <button type="button" className="simulator-step" aria-label="下一句" onClick={() => step(1)}>
            <span aria-hidden="true">›</span>
          </button>
        </div>
        <p className="simulator-caption">
          第 {sentenceIndex + 1} 句・{sentence.voice}聲<span>（共 {data.sentences.length} 句）</span>
        </p>
        <div className="simulator-switch" role="group" aria-label="怎麼聽">
          <button type="button" aria-pressed={!normal} onClick={() => setNormal(false)}>
            模擬
          </button>
          <button type="button" aria-pressed={normal} onClick={() => setNormal(true)}>
            正常聽
          </button>
        </div>
        <div className="simulator-switch" role="group" aria-label="在哪裡">
          <button type="button" aria-pressed={!restaurant} onClick={() => setRestaurant(false)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M4 11l8-6 8 6M6 10v9h12v-9" />
            </svg>
            安靜
          </button>
          <button type="button" aria-pressed={restaurant} onClick={() => setRestaurant(true)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path d="M7 3v8a2 2 0 0 0 2 2v8M11 3v8a2 2 0 0 1-2 2M17 3c-1.7 1.2-2.5 3.5-2.5 6.5 0 2 1 3.5 2.5 3.5v8" />
            </svg>
            餐廳
          </button>
        </div>
        <button type="button" className="simulator-reveal" aria-expanded={revealed} aria-controls={saidId} onClick={() => setRevealed(!revealed)}>
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M6 9l6 6 6-6" />
          </svg>
          {revealed ? "收起這句話" : "顯示這句話"}
        </button>
        <div id={saidId}>{revealed && <p className="simulator-said">{sentence.text}</p>}</div>
      </section>
      <div className="tip-box">
        {!normal && level.note && <p>{level.note}</p>}
        {data.limits.map((limit) => (
          <p key={limit}>{limit}</p>
        ))}
      </div>
    </>
  );
}
