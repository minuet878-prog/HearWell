import { impulseResponse } from "./simulator.js";

// The hearing loss simulator's sound (#487, ADR 0052), by Web Audio: a sentence plays through one
// ConvolverNode a curve (a degree, or 正常聽), each behind its own volume; picking another curve
// fades that one in and the last one out, so what plays goes on without a click. Nothing is built
// or downloaded before the first press of play: browsers (iOS above all) let sound start only from
// a tap, and a sentence downloads when first played.

// Seconds for a fade to settle: quick enough to hear as instant, slow enough not to click.
const GLIDE = 0.02;

export function createEngine(frequencies) {
  let context = null;
  let source = null;
  let curve = null;
  // A path a curve, by its thresholds: { convolver, volume }.
  const paths = new Map();
  // Each play() takes a ticket; a sentence still downloading for an older ticket does not start.
  let ticket = 0;
  const buffers = new Map();

  function path(thresholds) {
    const key = thresholds.join(",");
    if (!paths.has(key)) {
      const samples = Float32Array.from(impulseResponse(frequencies, thresholds, context.sampleRate));
      const impulse = context.createBuffer(1, samples.length, context.sampleRate);
      impulse.copyToChannel(samples, 0);
      // The filter's own levels are the point: no normalising.
      const convolver = new ConvolverNode(context, { buffer: impulse, disableNormalization: true });
      const volume = new GainNode(context, { gain: 0 });
      convolver.connect(volume).connect(context.destination);
      if (source) source.connect(convolver);
      paths.set(key, { convolver, volume });
    }
    return paths.get(key);
  }

  // Fade the current curve in and every other one out.
  function listen() {
    const current = path(curve);
    for (const { volume } of paths.values()) {
      volume.gain.setTargetAtTime(volume === current.volume ? 1 : 0, context.currentTime, GLIDE);
    }
  }

  function load(url) {
    if (!buffers.has(url)) {
      const loading = fetch(url)
        .then((response) => response.arrayBuffer())
        .then((bytes) => context.decodeAudioData(bytes));
      // A failed download is tried again on the next press.
      loading.catch(() => buffers.delete(url));
      buffers.set(url, loading);
    }
    return buffers.get(url);
  }

  function stop() {
    ticket += 1;
    if (source) {
      source.onended = null;
      source.stop();
      source = null;
    }
  }

  return {
    setCurve(thresholds) {
      curve = thresholds;
      if (context) listen();
    },

    stop,

    play(url, onEnded) {
      stop();
      const mine = ticket;
      // Built and resumed while still inside the tap. Safari: play through the silent switch, as
      // a video would.
      if (!context) {
        if (navigator.audioSession) navigator.audioSession.type = "playback";
        context = new AudioContext();
        listen();
      }
      context.resume();
      load(url)
        .then((buffer) => {
          if (mine !== ticket) return;
          source = new AudioBufferSourceNode(context, { buffer });
          for (const { convolver } of paths.values()) source.connect(convolver);
          source.onended = () => {
            source = null;
            onEnded();
          };
          source.start();
        })
        .catch(() => {
          if (mine === ticket) onEnded();
        });
    },
  };
}
