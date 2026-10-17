// Procedural 3D sound effects (no audio files needed).
import * as THREE from 'three';

let ctx = null;
const buffers = {};

function makeBuffer(seconds, fn) {
  const rate = ctx.sampleRate;
  const buf = ctx.createBuffer(1, Math.floor(seconds * rate), rate);
  const d = buf.getChannelData(0);
  let state = { lp: 0 };
  for (let i = 0; i < d.length; i++) d[i] = fn(i / rate, state);
  return buf;
}

const noise = () => Math.random() * 2 - 1;

function build() {
  // Gunshots: a sharp crack plus a low boom, each weapon with its own color.
  const shot = (len, boomHz, crack, decay) => makeBuffer(len, (t, s) => {
    const env = Math.exp(-t * decay);
    s.lp += (noise() - s.lp) * (crack * Math.exp(-t * 30) + 0.08);
    const boom = Math.sin(2 * Math.PI * boomHz * t * (1 - t)) * Math.exp(-t * 14);
    return (s.lp * 0.9 + boom * 0.7) * env;
  });
  buffers.pistol = shot(0.45, 90, 0.9, 9);
  buffers.smg = shot(0.3, 110, 0.8, 14);
  buffers.shotgun = shot(0.8, 60, 1.0, 6);
  buffers.npcShot = shot(0.4, 130, 0.6, 11);
  buffers.step = makeBuffer(0.12, (t, s) => {
    s.lp += (noise() - s.lp) * 0.12;
    return s.lp * Math.exp(-t * 40) * 2.2;
  });
  buffers.impact = makeBuffer(0.15, (t, s) => {
    s.lp += (noise() - s.lp) * 0.35;
    return s.lp * Math.exp(-t * 35);
  });
  buffers.flesh = makeBuffer(0.18, (t, s) => {
    s.lp += (noise() - s.lp) * 0.08;
    return (s.lp * 2 + Math.sin(2 * Math.PI * 70 * t) * 0.5) * Math.exp(-t * 25);
  });
  buffers.tink = makeBuffer(0.25, (t) => (Math.sin(2 * Math.PI * 3200 * t) + 0.5 * Math.sin(2 * Math.PI * 5100 * t)) * Math.exp(-t * 22) * 0.3);
  buffers.click = makeBuffer(0.05, (t) => noise() * Math.exp(-t * 120) * 0.6);
  buffers.magIn = makeBuffer(0.12, (t) => (noise() * 0.5 + Math.sin(2 * Math.PI * 900 * t)) * Math.exp(-t * 50) * 0.7);
  buffers.whoosh = makeBuffer(0.3, (t, s) => {
    s.lp += (noise() - s.lp) * 0.05;
    return s.lp * Math.sin(Math.PI * t / 0.3) * 1.5;
  });
  buffers.hurt = makeBuffer(0.35, (t) => Math.sign(Math.sin(2 * Math.PI * (120 - t * 120) * t)) * Math.exp(-t * 8) * 0.25);
  buffers.bell = makeBuffer(1.2, (t) => (Math.sin(2 * Math.PI * 660 * t) + 0.6 * Math.sin(2 * Math.PI * 990 * t)) * Math.exp(-t * 3) * 0.3);
}

export function initAudio() {
  if (ctx) { ctx.resume(); return; }
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  ctx = new AC();
  build();
  ctx.resume();
}

const _m = new THREE.Matrix4();
const _p = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3();
const _f = new THREE.Vector3();
const _u = new THREE.Vector3();
export function updateListener(camera) {
  if (!ctx) return;
  _m.copy(camera.matrixWorld);
  _m.decompose(_p, _q, _s);
  _f.set(0, 0, -1).applyQuaternion(_q);
  _u.set(0, 1, 0).applyQuaternion(_q);
  const l = ctx.listener;
  if (l.positionX) {
    l.positionX.value = _p.x; l.positionY.value = _p.y; l.positionZ.value = _p.z;
    l.forwardX.value = _f.x; l.forwardY.value = _f.y; l.forwardZ.value = _f.z;
    l.upX.value = _u.x; l.upY.value = _u.y; l.upZ.value = _u.z;
  } else {
    l.setPosition(_p.x, _p.y, _p.z);
    l.setOrientation(_f.x, _f.y, _f.z, _u.x, _u.y, _u.z);
  }
}

// Play a sound at a world position (or non-positional if pos is null).
export function play(name, pos = null, volume = 1, rate = 1) {
  if (!ctx || !buffers[name] || ctx.state !== 'running') return;
  const src = ctx.createBufferSource();
  src.buffer = buffers[name];
  src.playbackRate.value = rate * (0.94 + Math.random() * 0.12);
  const gain = ctx.createGain();
  gain.gain.value = volume;
  src.connect(gain);
  if (pos) {
    const pan = ctx.createPanner();
    pan.panningModel = 'equalpower';
    pan.distanceModel = 'inverse';
    pan.refDistance = 1.5;
    pan.rolloffFactor = 1.2;
    if (pan.positionX) { pan.positionX.value = pos.x; pan.positionY.value = pos.y; pan.positionZ.value = pos.z; }
    else pan.setPosition(pos.x, pos.y, pos.z);
    gain.connect(pan);
    pan.connect(ctx.destination);
  } else {
    gain.connect(ctx.destination);
  }
  src.start();
}
