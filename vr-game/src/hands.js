// Physics hands: rigid bodies that chase the tracked controllers (or tracked hands),
// collide with the world, push props, and grab / throw / holster things.
import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { world, G, materials, driveToPose, setPose, distToBody } from './physics.js';
import { state } from './state.js';
import { play } from './audio.js';
import { spawnAmmoInHand } from './weapons.js';

const _m = new THREE.Matrix4();
const _v = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3(1, 1, 1);

function handModel(color) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.7 });
  const palm = new THREE.Mesh(new THREE.BoxGeometry(0.085, 0.03, 0.09), mat);
  palm.castShadow = true;
  g.add(palm);
  const fingers = [];
  for (let i = 0; i < 4; i++) {
    const pivot = new THREE.Group();
    pivot.position.set(-0.03 + i * 0.02, 0, -0.045);
    const f = new THREE.Mesh(new THREE.BoxGeometry(0.017, 0.018, 0.075), mat);
    f.position.z = -0.035;
    pivot.add(f);
    g.add(pivot);
    fingers.push(pivot);
  }
  const thumb = new THREE.Group();
  thumb.position.set(0.045, -0.005, 0.0);
  const t = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.02, 0.06), mat);
  t.position.z = -0.03;
  thumb.add(t);
  thumb.rotation.y = -0.5;
  g.add(thumb);
  return { group: g, fingers, thumb };
}

export class Hand {
  constructor(side) {
    this.side = side;               // 'left' | 'right'
    this.sign = side === 'left' ? -1 : 1;
    this.source = null;             // XRInputSource
    this.ray = null; this.grip = null; this.xrHand = null; // three.js controller objects
    this.tracked = false;
    this.local = { pos: new THREE.Vector3(this.sign * 0.2, 1.2, -0.3), quat: new THREE.Quaternion() };
    this.target = { pos: new THREE.Vector3(), quat: new THREE.Quaternion() };
    this.recoilPos = 0; this.recoilRot = 0;

    this.gripValue = 0; this.triggerValue = 0;
    this.gripDown = false; this.triggerDown = false;
    this.buttons = { a: false, b: false, stick: false };
    this.prev = { grip: false, trigger: false, a: false, b: false, stick: false };
    this.stick = new THREE.Vector2();

    this.held = null;     // { kind: 'item'|'support'|'prop', item?, body?, constraint? }
    this.history = [];    // recent world positions for throw velocity
    this.velocity = new THREE.Vector3();

    this.body = new CANNON.Body({ mass: 1.5, material: materials.hand,
      collisionFilterGroup: G.HAND, collisionFilterMask: G.WORLD | G.PROP | G.NPC });
    // Palm faces inward, as when holding a controller or a gun grip.
    this.body.addShape(new CANNON.Box(new CANNON.Vec3(0.025, 0.045, 0.07)));
    this.body.allowSleep = false;
    this.body.linearDamping = 0;
    world.addBody(this.body);

    const model = handModel(0xd9a77e);
    this.model = model;
    model.group.rotation.z = -this.sign * Math.PI / 2;
    model.group.position.x = this.sign * 0.025;
    if (side === 'right') model.group.scale.x = -1; // the base model is a left hand
    this.mesh = new THREE.Group();
    this.mesh.add(model.group);
    state.scene.add(this.mesh);

    // Joints for articulated hand tracking.
    this.jointMeshes = new Map();
    this.jointMat = new THREE.MeshStandardMaterial({ color: 0xd9a77e });
    this.jointGeo = new THREE.SphereGeometry(0.009, 6, 4);
  }

  attach(source, ray, grip, xrHand) {
    this.source = source; this.ray = ray; this.grip = grip; this.xrHand = xrHand;
  }
  detach() { this.source = null; this.tracked = false; }

  pulse(intensity, ms) {
    const act = this.source && this.source.gamepad && this.source.gamepad.hapticActuators;
    if (act && act[0] && act[0].pulse) act[0].pulse(intensity, ms);
  }

  // Read tracking + buttons for this frame (VR).
  readXR() {
    const src = this.source;
    if (!src) { this.tracked = false; return; }
    if (src.hand && this.xrHand && this.xrHand.joints && this.xrHand.joints.wrist) {
      this.readTrackedHand();
      return;
    }
    if (!this.ray || !this.ray.visible) { this.tracked = false; return; }
    this.tracked = true;
    this.local.pos.copy(this.grip && this.grip.visible ? this.grip.position : this.ray.position);
    this.local.quat.copy(this.ray.quaternion);
    // Put the palm slightly behind the grip origin.
    this.local.pos.add(_v.set(0, -0.01, 0.03).applyQuaternion(this.local.quat));
    const gp = src.gamepad;
    if (gp) {
      const b = gp.buttons;
      this.triggerValue = b[0] ? b[0].value : 0;
      this.gripValue = b[1] ? b[1].value : 0;
      this.buttons.stick = !!(b[3] && b[3].pressed);
      this.buttons.a = !!(b[4] && b[4].pressed);
      this.buttons.b = !!(b[5] && b[5].pressed);
      this.stick.set(gp.axes[2] || 0, gp.axes[3] || 0);
    }
    this.triggerDown = this.triggerValue > 0.55;
    this.gripDown = this.gripValue > 0.5;
    this.showJoints(false);
  }

  readTrackedHand() {
    const j = this.xrHand.joints;
    const wrist = j.wrist, palm = j['middle-finger-metacarpal'];
    if (!wrist || !wrist.visible) { this.tracked = false; return; }
    this.tracked = true;
    // Aim frame: forward along the fingers, up toward the thumb.
    _q.setFromAxisAngle(_v.set(0, 0, 1), this.side === 'right' ? Math.PI / 2 : -Math.PI / 2);
    this.local.quat.copy(wrist.quaternion).multiply(_q);
    this.local.pos.copy(palm && palm.visible ? palm.position : wrist.position);
    const dist = (a, b) => (j[a] && j[b] ? j[a].position.distanceTo(j[b].position) : 1);
    const curl = (dist('middle-finger-tip', 'wrist') + dist('ring-finger-tip', 'wrist')) / 2;
    this.gripValue = THREE.MathUtils.clamp((0.15 - curl) / 0.06, 0, 1);
    const index = dist('index-finger-tip', 'index-finger-metacarpal');
    const pinch = dist('index-finger-tip', 'thumb-tip');
    this.triggerValue = Math.max(THREE.MathUtils.clamp((0.09 - index) / 0.03, 0, 1),
      this.held ? 0 : THREE.MathUtils.clamp((0.03 - pinch) / 0.015, 0, 1));
    this.gripDown = this.gripValue > 0.5;
    this.triggerDown = this.triggerValue > 0.6;
    this.buttons.a = this.buttons.b = this.buttons.stick = false;
    this.stick.set(0, 0);
    this.showJoints(true);
  }

  showJoints(on) {
    if (!this.xrHand || !this.xrHand.joints) return;
    for (const [name, joint] of Object.entries(this.xrHand.joints)) {
      let m = this.jointMeshes.get(name);
      if (!m) {
        m = new THREE.Mesh(this.jointGeo, this.jointMat);
        joint.add(m);
        this.jointMeshes.set(name, m);
      }
      m.visible = on && !this.held;
    }
    this.mesh.visible = !on || !!this.held;
  }

  edge(name, now) {
    const was = this.prev[name];
    this.prev[name] = now;
    return now && !was ? 1 : !now && was ? -1 : 0;
  }

  // World-space target pose (call after the rig moved). Includes recoil kick.
  computeTarget() {
    const rig = state.rig;
    rig.updateMatrixWorld();
    _m.compose(this.local.pos, this.local.quat, _s).premultiply(rig.matrixWorld);
    _m.decompose(this.target.pos, this.target.quat, _v);
    if (this.recoilPos > 0 || this.recoilRot > 0) {
      this.target.pos.add(_v.set(0, this.recoilPos * 0.3, this.recoilPos).applyQuaternion(this.target.quat));
      this.target.quat.multiply(_q.setFromAxisAngle(_v.set(1, 0, 0), this.recoilRot));
    }
  }

  addRecoil(pos, rot) {
    this.recoilPos = Math.min(0.12, this.recoilPos + pos);
    this.recoilRot = Math.min(0.9, this.recoilRot + rot);
  }

  // Before each physics step: chase the target with the physics body and drive held items.
  preStep(h) {
    this.computeTarget();
    const b = this.body;
    if (!this.tracked) return;
    let tp = this.target.pos, tq = this.target.quat;
    if (this.held && this.held.kind === 'support') {
      const w = this.held.item;
      tp = w.foregripWorld(new THREE.Vector3());
      tq = w.mesh.quaternion;
    }
    if (b.position.distanceTo(tp) > 0.45) setPose(b, tp, tq);
    else driveToPose(b, tp, tq, h, 25);
  }

  // Hold pose for kinematically-held items: the physics hand pose.
  holdPose(pos, quat) {
    pos.copy(this.body.position);
    quat.copy(this.body.quaternion);
  }

  update(dt) {
    // Decay recoil
    this.recoilPos = Math.max(0, this.recoilPos - dt * 0.6);
    this.recoilRot = Math.max(0, this.recoilRot - dt * 4);

    // Throw velocity from history of the tracked target.
    this.history.push({ t: state.time, p: this.target.pos.clone() });
    while (this.history.length > 8) this.history.shift();
    const h0 = this.history[0], h1 = this.history[this.history.length - 1];
    if (h1.t - h0.t > 0) this.velocity.subVectors(h1.p, h0.p).divideScalar(h1.t - h0.t);

    // Visual hand at the physics pose.
    this.mesh.position.copy(this.body.position);
    this.mesh.quaternion.copy(this.body.quaternion);
    this.mesh.visible = this.tracked && (!this.held || this.held.kind !== 'item' || this.held.item.showHand !== false);
    const curl = this.held ? 1.3 : this.gripValue * 1.3;
    this.model.fingers.forEach((f, i) => { f.rotation.x = -(i === 0 && this.held && this.held.item && this.held.item.isWeapon ? this.triggerValue * 0.9 + 0.4 : curl); });
    this.model.thumb.rotation.x = -curl * 0.4;

    if (!this.tracked) return;
    const g = this.edge('grip', this.gripDown);
    if (g === 1) this.tryGrab();
    if (g === -1) this.release();
  }

  palm() { return _v.copy(this.body.position); }

  tryGrab() {
    if (this.held) return;
    const p = this.body.position.clone();
    const player = state.player;
    const other = state.hands.find((h) => h !== this);
    const otherItem = other && other.held && other.held.kind === 'item' ? other.held.item : null;

    // 1. A holstered weapon (unless the hand is closer to an ammo pouch)
    let slot = null, slotD = 0.18;
    for (const s of player.slots) {
      const d = s.pos.distanceTo(p);
      if (s.item && d < slotD) { slotD = d; slot = s; }
    }
    const pouchD = player.pouchDistance(p);
    const wantsAmmo = otherItem && otherItem.isWeapon && pouchD < 0.14 && pouchD < slotD;
    if (slot && !wantsAmmo) { this.grabItem(slot.item); return; }
    // 2. Support grip on a two-handed weapon held by the other hand
    if (otherItem && otherItem.isWeapon && otherItem.def.foregrip &&
        otherItem.foregripWorld(new THREE.Vector3()).distanceTo(p) < 0.15) {
      this.held = { kind: 'support', item: otherItem };
      otherItem.support = this;
      play('click', p, 0.4);
      this.pulse(0.3, 30);
      return;
    }
    // 3. Fresh ammo from the belt pouch for the weapon in the other hand
    if (wantsAmmo) {
      const ammo = spawnAmmoInHand(otherItem.def.key, this);
      if (ammo) { this.grabItem(ammo); return; }
    }
    // 4. Loose items (weapons, magazines) by their handle, then any grabbable body.
    let best = null, bd = 0.14;
    for (const body of state.grabbables) {
      const item = body.userData.item;
      let d;
      if (item) {
        if (item.holder === this || item.slot) continue;
        d = Math.min(item.gripWorld(new THREE.Vector3()).distanceTo(p), distToBody(body, p) + 0.08);
      } else {
        d = distToBody(body, p) + 0.06;
      }
      if (d < bd) { bd = d; best = body; }
    }
    if (!best) return;
    if (best.userData.item) this.grabItem(best.userData.item);
    else this.grabBody(best);
  }

  grabItem(item) {
    if (item.holder && item.holder !== this) item.holder.dropHeld(false);
    if (item.slot) { item.slot.item = null; item.slot = null; }
    this.held = { kind: 'item', item };
    item.onGrab(this);
    play('click', this.body.position, 0.5, 0.8);
    this.pulse(0.4, 40);
  }

  grabBody(body) {
    const mask = body.collisionFilterMask;
    body.collisionFilterMask = mask & ~(G.HAND | G.PLAYER);
    const c = new CANNON.LockConstraint(this.body, body, { maxForce: 900 });
    c.collideConnected = false;
    world.addConstraint(c);
    body.wakeUp();
    this.held = { kind: 'prop', body, constraint: c, mask };
    if (body.userData.npc) body.userData.npc.grabbed = (body.userData.npc.grabbed || 0) + 1;
    this.pulse(0.4, 40);
  }

  release() {
    if (!this.held) return;
    this.dropHeld(true);
  }

  // Let go of whatever is held. `throwIt` imparts hand velocity.
  dropHeld(throwIt) {
    const held = this.held;
    if (!held) return;
    this.held = null;
    if (held.kind === 'support') {
      held.item.support = null;
      return;
    }
    if (held.kind === 'prop') {
      world.removeConstraint(held.constraint);
      held.body.collisionFilterMask = held.mask;
      if (throwIt) {
        held.body.velocity.set(this.velocity.x, this.velocity.y, this.velocity.z);
        if (this.velocity.length() > 3) play('whoosh', held.body.position, 0.5);
      }
      if (held.body.userData.npc) held.body.userData.npc.grabbed--;
      return;
    }
    const item = held.item;
    // Holster weapons released near a free slot.
    if (throwIt && item.isWeapon) {
      const slot = state.player.freeSlotNear(this.body.position, item.def.holster);
      if (slot) { item.onRelease(this, null); item.holsterTo(slot); play('click', this.body.position, 0.4, 0.7); return; }
    }
    item.onRelease(this, throwIt ? this.velocity : null);
  }
}
