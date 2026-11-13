// The hearing loss simulator's sound (#487, ADR 0052), by Web Audio: a sentence plays through a
// chain of BiquadFilterNodes, one a band; a new degree or 正常聽 only moves the filters' gains, so
// what plays goes on. Nothing is built or downloaded before the first press of play: browsers
// (iOS above all) let sound start only from a tap, and a sentence downloads when first played.

// Seconds for a gain to settle: quick enough to hear as instant, slow enough not to click.
const GLIDE = 0.02;

export function createEngine() {
  let context = null;
  let filters = [];
  let bands = [];
  let source = null;
  // Each play() takes a ticket; a sentence still downloading for an older ticket does not start.
  let ticket = 0;
  const buffers = new Map();

  function build() {
    // Safari: play through the silent switch, as a video would.
    if (navigator.audioSession) navigator.audioSession.type = "playback";
    context = new AudioContext();
    filters = bands.map((band) => {
      const filter = context.createBiquadFilter();
      filter.type = band.type;
      filter.frequency.value = band.frequency;
      if (band.Q) filter.Q.value = band.Q;
      filter.gain.value = band.gain;
      return filter;
    });
    filters.reduce((from, to) => from.connect(to)).connect(context.destination);
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
    setBands(next) {
      bands = next;
      filters.forEach((filter, i) => filter.gain.setTargetAtTime(next[i].gain, context.currentTime, GLIDE));
    },

    stop,

    play(url, onEnded) {
      stop();
      const mine = ticket;
      // Built and resumed while still inside the tap.
      if (!context) build();
      context.resume();
      load(url)
        .then((buffer) => {
          if (mine !== ticket) return;
          source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(filters[0]);
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
