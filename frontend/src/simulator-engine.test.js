import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { createEngine } from "./simulator-engine.js";

// #488: the engine against stand-ins for Web Audio, which jsdom does not have. Each node records
// what it is connected to, so a test can follow the sound from a source to the speakers.
const FREQUENCIES = [250, 500, 1000, 2000, 4000, 8000];
const HIGH_FREQUENCY = [15, 20, 25, 45, 65, 75];
const SPEECH = "/static/sentence-1.m4a";
const RESTAURANT = "/static/restaurant.m4a";
// Square waves, so their loudness is their height: speech 0.1, restaurant 0.05.
const SAMPLES = {
  [SPEECH]: Float32Array.from({ length: 480 }, (_, n) => (n % 2 ? -0.1 : 0.1)),
  [RESTAURANT]: Float32Array.from({ length: 480 }, (_, n) => (n % 2 ? -0.05 : 0.05)),
};

let context;

class FakeNode {
  constructor(owner, options = {}) {
    this.options = options;
    this.outputs = [];
    owner.nodes.push(this);
  }

  connect(node) {
    this.outputs.push(node);
    return node;
  }
}

class FakeConvolverNode extends FakeNode {}

class FakeGainNode extends FakeNode {
  constructor(owner, options = {}) {
    super(owner, options);
    this.gain = {
      value: options.gain ?? 1,
      targets: [],
      setTargetAtTime(value) {
        this.value = value;
        this.targets.push(value);
      },
    };
  }
}

class FakeAudioBufferSourceNode extends FakeNode {
  constructor(owner, options = {}) {
    super(owner, options);
    this.buffer = options.buffer;
    this.loop = Boolean(options.loop);
    this.started = false;
    this.stopped = false;
  }

  start() {
    this.started = true;
  }

  stop(when = 0) {
    this.stopped = true;
    this.stopAt = when;
  }
}

class FakeAudioContext {
  constructor() {
    this.nodes = [];
    this.sampleRate = 48000;
    this.currentTime = 0;
    this.destination = { speakers: true };
    context = this;
  }

  createBuffer() {
    return { copyToChannel() {} };
  }

  resume() {
    return Promise.resolve();
  }

  // fetch below hands over the URL as the "bytes".
  decodeAudioData(url) {
    return Promise.resolve({ url, getChannelData: () => SAMPLES[url] });
  }
}

beforeEach(() => {
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("ConvolverNode", FakeConvolverNode);
  vi.stubGlobal("GainNode", FakeGainNode);
  vi.stubGlobal("AudioBufferSourceNode", FakeAudioBufferSourceNode);
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => Promise.resolve({ arrayBuffer: () => Promise.resolve(url) })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  context = undefined;
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const source = (url) => context.nodes.find((node) => node instanceof FakeAudioBufferSourceNode && node.buffer.url === url);
const fetched = () => fetch.mock.calls.map(([url]) => url);

// Every way from node to the speakers, as the nodes passed through.
function routes(node, passed = []) {
  if (node === context.destination) return [passed];
  return node.outputs.flatMap((next) => routes(next, [...passed, next]));
}
const filtersOn = (node) => new Set(routes(node).flatMap((route) => route.filter((n) => n instanceof FakeConvolverNode)));

async function playing({ restaurant }) {
  const engine = createEngine(FREQUENCIES, 5);
  const ended = vi.fn();
  engine.setCurve(HIGH_FREQUENCY);
  engine.setBackground(restaurant ? RESTAURANT : null);
  engine.play(SPEECH, ended);
  await settle();
  return { engine, ended };
}

it("mixes the restaurant into the speech before the filter, never round it", async () => {
  // #484 acceptance 10: the hearing loss turns both down alike.
  await playing({ restaurant: true });
  const speech = source(SPEECH);
  const restaurant = source(RESTAURANT);
  expect(speech.started && restaurant.started).toBe(true);
  for (const route of [...routes(speech), ...routes(restaurant)]) {
    expect(route.some((node) => node instanceof FakeConvolverNode)).toBe(true);
  }
  expect(filtersOn(restaurant)).toEqual(filtersOn(speech));
  expect(filtersOn(speech).size).toBeGreaterThan(0);
});

it("plays the restaurant 5 dB under the speech, over and over", async () => {
  // Speech 0.1, restaurant 0.05: up 1.1247 for 5 dB under (worked in simulator.test.js).
  await playing({ restaurant: true });
  const restaurant = source(RESTAURANT);
  expect(restaurant.loop).toBe(true);
  const volume = restaurant.outputs[0];
  expect(volume.gain.value).toBeCloseTo(1.1247, 4);
});

it("stops the restaurant when the sentence ends", async () => {
  // #484 acceptance 11.
  const { ended } = await playing({ restaurant: true });
  source(SPEECH).onended();
  expect(source(RESTAURANT).stopped).toBe(true);
  expect(ended).toHaveBeenCalledOnce();
});

it("downloads the restaurant only once picked, and starts it under what already plays", async () => {
  const { engine } = await playing({ restaurant: false });
  expect(fetched()).toEqual([SPEECH]);
  engine.setBackground(RESTAURANT);
  await settle();
  expect(fetched()).toEqual([SPEECH, RESTAURANT]);
  expect(source(RESTAURANT).started).toBe(true);
  expect(source(SPEECH).stopped).toBe(false);
});

it("takes the restaurant away without stopping the sentence", async () => {
  const { engine } = await playing({ restaurant: true });
  engine.setBackground(null);
  expect(source(RESTAURANT).stopped).toBe(true);
  expect(source(SPEECH).stopped).toBe(false);
});

it("stops both when the sentence is stopped", async () => {
  const { engine, ended } = await playing({ restaurant: true });
  engine.stop();
  expect(source(SPEECH).stopped).toBe(true);
  expect(source(RESTAURANT).stopped).toBe(true);
  expect(ended).not.toHaveBeenCalled();
});

it("starts the restaurant with the sentence the first time, not after it", async () => {
  // #488 review: the restaurant is the bigger download; the sentence waits for it.
  let arrive;
  fetch.mockImplementation((url) =>
    url === RESTAURANT
      ? new Promise((resolve) => {
          arrive = () => resolve({ arrayBuffer: () => Promise.resolve(url) });
        })
      : Promise.resolve({ arrayBuffer: () => Promise.resolve(url) }),
  );
  await playing({ restaurant: true });
  expect(source(SPEECH)).toBeUndefined();
  arrive();
  await settle();
  expect(source(SPEECH).started && source(RESTAURANT).started).toBe(true);
});

it("fades the restaurant in and out instead of clicking", async () => {
  const { engine } = await playing({ restaurant: true });
  const volume = source(RESTAURANT).outputs[0];
  expect(volume.options.gain).toBe(0);
  expect(volume.gain.targets.at(-1)).toBeCloseTo(1.1247, 4);
  engine.setBackground(null);
  expect(volume.gain.targets.at(-1)).toBe(0);
  expect(source(RESTAURANT).stopAt).toBeGreaterThan(context.currentTime);
});

it("keeps the restaurant going when the degree or 正常聽 changes", async () => {
  const { engine } = await playing({ restaurant: true });
  engine.setCurve([0, 0, 0, 0, 0, 0]);
  engine.setCurve([40, 45, 50, 55, 60, 65]);
  expect(source(RESTAURANT).stopped).toBe(false);
  expect(filtersOn(source(RESTAURANT))).toEqual(filtersOn(source(SPEECH)));
});

it("turns the two down 2 dB where they meet, so the loudest sentence does not clip", async () => {
  // #488 review: sentence 2 peaks at full scale and the restaurant took it 1.2% over.
  await playing({ restaurant: true });
  const [meet] = source(SPEECH).outputs;
  expect(source(RESTAURANT).outputs[0].outputs).toContain(meet);
  expect(meet.gain.value).toBeCloseTo(10 ** (-2 / 20), 6);
});
