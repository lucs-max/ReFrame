// Entry point: renderer, WebXR session, input mapping, desktop fallback and the main loop.
import * as THREE from 'three';
import { world, STEP, syncMeshes, raycast, G } from './physics.js';
import { state } from './state.js';
import { initAudio, updateListener } from './audio.js';
import { initEffects, updateEffects } from './effects.js';
import { buildWorld, updateButtons } from './world.js';
import { Player } from './player.js';
import { Hand } from './hands.js';
import { Weapon, itemsPreStep, updateItems } from './weapons.js';
import { npcsPreStep, updateNPCs } from './npc.js';
import { Game } from './game.js';

// --- Renderer, scene, rig -------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.xr.enabled = true;
renderer.xr.setReferenceSpaceType('local-floor');
renderer.xr.setFoveation(1);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.05, 200);
const rig = new THREE.Group();
rig.add(camera);
scene.add(rig);
Object.assign(state, { scene, camera, rig, renderer });

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// --- Game objects ---------------------------------------------------------------------
const game = state.game = new Game();
initEffects(scene);
buildWorld();
const player = state.player = new Player();
const hands = state.hands = [new Hand('left'), new Hand('right')];
const handBySide = { left: hands[0], right: hands[1] };
game.initHUD();

// Loadout: holstered pistol, SMG and shotgun; spares on the table.
const flat = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, Math.PI / 2, Math.PI / 2));
const loadout = { 'right hip': 'pistol', 'left hip': 'smg', back: 'shotgun' };
player.update(0);
for (const slot of player.slots) new Weapon(loadout[slot.name], slot.pos).holsterTo(slot);
new Weapon('pistol', new THREE.Vector3(1.0, 0.96, 7.1), flat);
new Weapon('smg', new THREE.Vector3(1.5, 0.96, 7.1), flat);
new Weapon('shotgun', new THREE.Vector3(1.6, 0.97, 7.4), flat);

// --- WebXR controllers ----------------------------------------------------------------
for (let i = 0; i < 2; i++) {
  const ray = renderer.xr.getController(i);
  const grip = renderer.xr.getControllerGrip(i);
  const xrHand = renderer.xr.getHand(i);
  rig.add(ray, grip, xrHand);
  ray.addEventListener('connected', (e) => {
    const src = e.data;
    const hand = handBySide[src.handedness];
    if (hand) { hand.attach(src, ray, grip, xrHand); ray.userData.hand = hand; }
  });
  ray.addEventListener('disconnected', () => {
    if (ray.userData.hand) ray.userData.hand.detach();
    ray.userData.hand = null;
  });
}

// --- Menu / session -------------------------------------------------------------------
const menu = document.getElementById('menu');
const vrBtn = document.getElementById('enter-vr');
const deskBtn = document.getElementById('play-desktop');
const status = document.getElementById('status');
const crosshair = document.getElementById('crosshair');

if (navigator.xr) {
  navigator.xr.isSessionSupported('immersive-vr').then((ok) => {
    vrBtn.disabled = !ok;
    status.textContent = ok ? 'VR headset ready.' : 'No VR headset found: you can still play on desktop.';
  }).catch(() => { status.textContent = 'WebXR unavailable: play on desktop.'; });
} else {
  status.textContent = window.isSecureContext
    ? 'This browser has no WebXR: play on desktop, or open this page in your headset\'s browser.'
    : 'WebXR needs HTTPS (or localhost). Play on desktop, or serve the page over HTTPS.';
}

vrBtn.addEventListener('click', async () => {
  initAudio();
  const base = ['local-floor', 'bounded-floor', 'hand-tracking'];
  let session;
  try {
    session = await navigator.xr.requestSession('immersive-vr', { optionalFeatures: [...base, 'body-tracking'] });
  } catch {
    session = await navigator.xr.requestSession('immersive-vr', { optionalFeatures: base });
  }
  session.addEventListener('end', () => {
    state.inVR = false;
    menu.classList.remove('hidden');
  });
  await renderer.xr.setSession(session);
  state.inVR = true;
  state.desktop = false;
  menu.classList.add('hidden');
  crosshair.style.display = 'none';
  game.domHud.style.display = 'none';
});

deskBtn.addEventListener('click', () => {
  initAudio();
  state.desktop = true;
  menu.classList.add('hidden');
  crosshair.style.display = 'block';
  game.domHud.style.display = 'block';
  renderer.domElement.requestPointerLock?.();
  if (!handBySide.right.held) equip('pistol');
});

// --- Desktop controls -----------------------------------------------------------------
const keys = new Set();
const desk = state.desk = { yaw: 0, pitch: 0, crouch: false, fire: false };
renderer.domElement.addEventListener('click', () => {
  if (state.desktop && document.pointerLockElement !== renderer.domElement) renderer.domElement.requestPointerLock?.();
});
document.addEventListener('mousemove', (e) => {
  if (!state.desktop || document.pointerLockElement !== renderer.domElement) return;
  if (Math.abs(e.movementX) > 300 || Math.abs(e.movementY) > 300) return; // spike when the lock engages
  desk.yaw -= e.movementX * 0.0022;
  desk.pitch = THREE.MathUtils.clamp(desk.pitch - e.movementY * 0.0022, -1.45, 1.45);
});
document.addEventListener('mousedown', (e) => { if (state.desktop && e.button === 0) desk.fire = true; });
document.addEventListener('mouseup', (e) => { if (e.button === 0) desk.fire = false; });
document.addEventListener('keydown', (e) => {
  if (!state.desktop) return;
  keys.add(e.code);
  const right = handBySide.right;
  if (e.code === 'KeyE') deskGrab();
  if (e.code === 'KeyQ' && right.held) {
    const f = new THREE.Vector3(0, 0, -1).applyQuaternion(player.headQuat);
    right.velocity.copy(f).multiplyScalar(9).add(new THREE.Vector3(0, 1.5, 0));
    right.dropHeld(true);
  }
  if (e.code === 'KeyR') {
    const it = right.held && right.held.item;
    if (it && it.isWeapon) it.instantReload();
  }
  if (e.code === 'Digit1') equip('pistol');
  if (e.code === 'Digit2') equip('smg');
  if (e.code === 'Digit3') equip('shotgun');
  if (e.code === 'KeyC') desk.crouch = !desk.crouch;
  if (e.code === 'Enter') game.startWave();
  if (e.code === 'KeyT') game.toggleHostile();
  if (e.code === 'KeyV') player.locomotion = player.locomotion === 'stick' ? 'swing' : 'stick';
});
document.addEventListener('keyup', (e) => keys.delete(e.code));

function equip(key) {
  const right = handBySide.right;
  const cur = right.held && right.held.kind === 'item' ? right.held.item : null;
  if (cur && cur.isWeapon && cur.def.key === key) return;
  const w = state.weapons.find((x) => x.def.key === key && x.slot) ||
    state.weapons.find((x) => x.def.key === key && !x.holder);
  if (!w) return;
  if (cur) {
    const slot = cur.isWeapon && player.slots.find((s) => !s.item && s.accepts.includes(cur.def.holster));
    right.dropHeld(false);
    if (slot) cur.holsterTo(slot);
  }
  right.grabItem(w);
}

function deskGrab() {
  const right = handBySide.right;
  const from = player.headWorld.clone();
  const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(player.headQuat);
  const hit = raycast(from, from.clone().addScaledVector(dir, 3.5), G.PROP | G.NPC | G.WORLD);
  if (!hit || !state.grabbables.has(hit.body)) return;
  const cur = right.held && right.held.kind === 'item' ? right.held.item : null;
  if (cur && cur.isWeapon) {
    const slot = player.slots.find((s) => !s.item && s.accepts.includes(cur.def.holster));
    right.dropHeld(false);
    if (slot) cur.holsterTo(slot);
  } else if (right.held) right.dropHeld(false);
  const body = hit.body;
  if (body.userData.item) { right.grabItem(body.userData.item); return; }
  if (body.mass <= 15 && !body.userData.npc) {
    body.position.set(right.body.position.x, right.body.position.y, right.body.position.z);
    body.velocity.set(0, 0, 0);
  }
  right.grabBody(body);
}

const _hq = new THREE.Quaternion();
const _m = new THREE.Matrix4();
function desktopInput() {
  const headH = desk.crouch ? 1.05 : 1.65;
  _hq.setFromEuler(new THREE.Euler(desk.pitch, desk.yaw, 0, 'YXZ'));
  // Keep the head centered over the body; the rig carries position.
  player.setHead(new THREE.Vector3(0, headH, 0), _hq);
  const mv = player.input.move.set(0, 0);
  if (keys.has('KeyW')) mv.y += 1;
  if (keys.has('KeyS')) mv.y -= 1;
  if (keys.has('KeyD')) mv.x += 1;
  if (keys.has('KeyA')) mv.x -= 1;
  player.input.sprint = keys.has('ShiftLeft') || keys.has('ShiftRight');
  player.input.jump = keys.has('Space');

  // Hands float in front of the view; the gun converges on what the crosshair points at.
  player.computeHeadWorld();
  const right = handBySide.right, left = handBySide.left;
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(player.headQuat);
  const hit = raycast(player.headWorld, player.headWorld.clone().addScaledVector(fwd, 80), G.WORLD | G.PROP | G.NPC);
  const aimWorld = hit && hit.distance > 1 ? hit.point : player.headWorld.clone().addScaledVector(fwd, 80);
  const aimLocal = rig.worldToLocal(aimWorld.clone());
  right.local.pos.set(0.17, -0.2, -0.4).applyQuaternion(_hq).add(player.headLocal);
  _m.lookAt(right.local.pos, aimLocal, new THREE.Vector3(0, 1, 0).applyQuaternion(_hq));
  right.local.quat.setFromRotationMatrix(_m);
  left.local.pos.set(-0.2, -0.32, -0.3).applyQuaternion(_hq).add(player.headLocal);
  left.local.quat.copy(_hq);
  for (const h of hands) { h.tracked = true; h.gripDown = !!h.held; h.prev.grip = h.gripDown; }
  right.triggerDown = desk.fire;
  right.triggerValue = desk.fire ? 1 : 0;
}

// --- VR input -------------------------------------------------------------------------
const turn = { ready: true };
const prevLocalY = { left: 0, right: 0 };
function vrInput(frame, dt) {
  const ref = renderer.xr.getReferenceSpace();
  const pose = frame.getViewerPose(ref);
  if (pose) {
    const t = pose.transform;
    player.setHead(new THREE.Vector3(t.position.x, t.position.y, t.position.z),
      new THREE.Quaternion(t.orientation.x, t.orientation.y, t.orientation.z, t.orientation.w));
  }
  // Optional full body tracking: use the real chest when the runtime provides it.
  player.chestTracked = null;
  try {
    const chest = frame.body && frame.body.get && frame.body.get('chest');
    const cp = chest && frame.getPose(chest, ref);
    if (cp) {
      const t = cp.transform;
      player.chestTracked = {
        pos: new THREE.Vector3(t.position.x, t.position.y, t.position.z),
        quat: new THREE.Quaternion(t.orientation.x, t.orientation.y, t.orientation.z, t.orientation.w),
      };
    }
  } catch { /* body tracking not supported */ }

  for (const h of hands) h.readXR();
  const left = handBySide.left, right = handBySide.right;
  player.input.move.set(left.stick.x, -left.stick.y);
  player.input.sprint = left.buttons.stick || (player.input.sprint && player.input.move.length() > 0.3);

  // Right stick: snap turn and jump.
  const rx = right.stick.x, ry = right.stick.y;
  if (Math.abs(rx) > 0.7 && turn.ready) { player.snapTurn(-Math.sign(rx) * Math.PI / 6); turn.ready = false; }
  if (Math.abs(rx) < 0.3) turn.ready = true;
  player.input.jump = ry < -0.75;

  if (left.edge('b', left.buttons.b) === 1) {
    player.locomotion = player.locomotion === 'stick' ? 'swing' : 'stick';
    game.say(player.locomotion === 'swing' ? 'Arm-swing walking: swing your arms' : 'Stick walking');
  }
  if (right.edge('b', right.buttons.b) === 1) game.startWave();

  // Arm swing: vertical hand speed relative to the head.
  const headY = player.headLocal.y;
  const vy = {};
  for (const h of hands) {
    const rel = h.local.pos.y - headY;
    vy[h.side] = dt > 0 ? (rel - prevLocalY[h.side]) / dt : 0;
    prevLocalY[h.side] = rel;
  }
  player.updateSwing(dt, vy.left, vy.right);
}

// --- Main loop ------------------------------------------------------------------------
const clock = new THREE.Clock();
let acc = 0;
renderer.setAnimationLoop((time, frame) => {
  const dt = Math.min(clock.getDelta(), 0.05);
  state.time += dt;

  if (frame && renderer.xr.isPresenting) vrInput(frame, dt);
  else if (state.desktop) desktopInput();
  else {
    // Attract mode: slowly look around the arena behind the menu.
    player.setHead(new THREE.Vector3(0, 1.65, 0), new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.05, Math.sin(state.time * 0.15) * 0.6, 0)));
    for (const h of hands) h.tracked = false;
  }
  if (!renderer.xr.isPresenting) {
    camera.position.copy(player.headLocal);
    camera.quaternion.copy(player.headLocalQuat);
  }

  acc += dt;
  let steps = 0;
  while (acc >= STEP && steps < 5) {
    player.preStep(STEP);
    for (const h of hands) h.preStep(STEP);
    itemsPreStep(STEP);
    npcsPreStep(STEP);
    world.step(STEP);
    player.syncRig();
    acc -= STEP;
    steps++;
  }
  if (steps === 5) acc = 0;
  syncMeshes();

  for (const h of hands) h.update(dt);
  updateItems(dt);
  player.update(dt);
  updateNPCs(dt);
  game.update(dt);
  updateButtons(dt, hands.filter((h) => h.tracked && !h.held).map((h) =>
    new THREE.Vector3(0, 0, -0.08).applyQuaternion(h.mesh.quaternion).add(h.mesh.position)));
  updateEffects(dt);
  updateListener(camera);
  renderer.render(scene, camera);
});

// Handy for debugging from the console.
window.game = state;
