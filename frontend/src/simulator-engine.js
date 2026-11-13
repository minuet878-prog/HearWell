import { backgroundVolume, impulseResponse, loudness } from "./simulator.js";

// The hearing loss simulator's sound (#487, ADR 0052), by Web Audio. The sentence, and under it the
// restaurant (#488), meet in one mix before any filter: the hearing loss turns both down alike.
// The mix plays through one ConvolverNode a curve (a degree, or 正常聽), each behind its own volume;
// picking another curve fades that one in and the last one out, so what plays goes on without a
// click. Nothing is built or downloaded before the first press of play: browsers (iOS above all)
// let sound start only from a tap, and a sound downloads when first needed.

// Seconds for a fade to settle: quick enough to hear as instant, slow enough not to click.
const GLIDE = 0.02;
// Room left where the two meet: sentence 2 peaks at full scale, and the restaurant on top took it
// 1.2% over (#488 review).
const HEADROOM = 10 ** (-2 / 20);

export function createEngine(frequencies, snr) {
  let context = null;
  let mix = null;
  let source = null;
  let speechLoudness = 0;
  let curve = null;
  // The restaurant's address while 餐廳 is picked; its sound and volume while it plays.
  let backgroundUrl = null;
  let restaurant = null;
  // A path a curve, by its thresholds: { convolver, volume }.
  const paths = new Map();
  // Each play() takes a ticket; a sound still downloading for an older ticket does not start.
  let ticket = 0;
  const buffers = new Map();
  // Each decoded sound's loudness, worked out once.
  const levels = new Map();

  function level(buffer) {
    if (!levels.has(buffer)) levels.set(buffer, loudness(buffer.getChannelData(0)));
    return levels.get(buffer);
  }

  function path(thresholds) {
    const key = thresholds.join(",");
    if (!paths.has(key)) {
      const samples = Float32Array.from(impulseResponse(frequencies, thresholds, context.sampleRate));
      const impulse = context.createBuffer(1, samples.length, context.sampleRate);
      impulse.copyToChannel(samples, 0);
      // The filter's own levels are the point: no normalising.
      const convolver = new ConvolverNode(context, { buffer: impulse, disableNormalization: true });
      const volume = new GainNode(context, { gain: 0 });
      mix.connect(convolver).connect(volume).connect(context.destination);
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
      // A failed download is tried again next time it is needed.
      loading.catch(() => buffers.delete(url));
      buffers.set(url, loading);
    }
    return buffers.get(url);
  }

  // The restaurant, snr dB under the sentence playing now, faded in, round and round.
  function startRestaurant(buffer) {
    const volume = new GainNode(context, { gain: 0 });
    const playing = new AudioBufferSourceNode(context, { buffer, loop: true });
    playing.connect(volume).connect(mix);
    volume.gain.setTargetAtTime(backgroundVolume(speechLoudness, level(buffer), snr), context.currentTime, GLIDE);
    playing.start();
    restaurant = { playing, volume };
  }

  // Faded out, then stopped.
  function stopRestaurant() {
    if (restaurant) {
      restaurant.volume.gain.setTargetAtTime(0, context.currentTime, GLIDE);
      restaurant.playing.stop(context.currentTime + 5 * GLIDE);
      restaurant = null;
    }
  }

  // 餐廳 picked while a sentence plays, or before its download came: the restaurant joins it.
  function joinRestaurant() {
    const url = backgroundUrl;
    const mine = ticket;
    load(url)
      .then((buffer) => {
        if (mine === ticket && source && backgroundUrl === url && !restaurant) startRestaurant(buffer);
      })
      // Without it the sentence goes on alone.
      .catch(() => {});
  }

  function stop() {
    ticket += 1;
    stopRestaurant();
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

    setBackground(url) {
      backgroundUrl = url;
      stopRestaurant();
      if (url && source) joinRestaurant();
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
        mix = new GainNode(context, { gain: HEADROOM });
        listen();
      }
      context.resume();
      // With 餐廳 the sentence waits for the restaurant, the bigger download, so they start
      // together; a restaurant that fails to download leaves the sentence alone.
      const wanted = backgroundUrl;
      Promise.all([load(url), wanted ? load(wanted).catch(() => null) : null])
        .then(([buffer, background]) => {
          if (mine !== ticket) return;
          speechLoudness = level(buffer);
          source = new AudioBufferSourceNode(context, { buffer });
          source.connect(mix);
          source.onended = () => {
            source = null;
            stopRestaurant();
            onEnded();
          };
          source.start();
          if (background && backgroundUrl === wanted) startRestaurant(background);
          else if (backgroundUrl) joinRestaurant();
        })
        .catch(() => {
          if (mine === ticket) onEnded();
        });
    },
  };
}
