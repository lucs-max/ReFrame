// Weapons and ammo: rigid-body items you can grab, holster, throw, shoot and reload by hand.
import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { world, G, materials, link, unlink, driveToPose, setPose, raycast, toThree } from './physics.js';
import { state } from './state.js';
import { play } from './audio.js';
import { tracer, muzzleFlash, burst, bulletHole } from './effects.js';

export const DEFS = {
  pistol: {
    key: 'pistol', name: 'Pistol', auto: false, rpm: 420, damage: 34, pellets: 1, spread: 0.004,
    cap: 15, feed: 'mag', recoil: [0.035, 0.22], impulse: 6, mass: 1.0, holster: 'hip', sound: 'pistol',
    foregrip: null,
  },
  smg: {
    key: 'smg', name: 'SMG', auto: true, rpm: 780, damage: 22, pellets: 1, spread: 0.014,
    cap: 30, feed: 'mag', recoil: [0.018, 0.09], impulse: 5, mass: 2.4, holster: 'hip', sound: 'smg',
    foregrip: new THREE.Vector3(0, -0.03, -0.2),
  },
  shotgun: {
    key: 'shotgun', name: 'Shotgun', auto: false, rpm: 75, damage: 14, pellets: 9, spread: 0.045,
    cap: 6, feed: 'shell', recoil: [0.09, 0.6], impulse: 4, mass: 3.4, holster: 'back', sound: 'shotgun',
    foregrip: new THREE.Vector3(0, 0.03, -0.4),
  },
};

const mats = {
  metal: new THREE.MeshStandardMaterial({ color: 0x2a2d31, roughness: 0.45, metalness: 0.6 }),
  dark: new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 0.7 }),
  wood: new THREE.MeshStandardMaterial({ color: 0x6b4426, roughness: 0.8 }),
  brass: new THREE.MeshStandardMaterial({ color: 0xc9a443, roughness: 0.35, metalness: 0.8 }),
  shell: new THREE.MeshStandardMaterial({ color: 0xb02a22, roughness: 0.6 }),
  sight: new THREE.MeshBasicMaterial({ color: 0x7dff6a }),
};

function box(g, w, h, d, x, y, z, mat, rx = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  m.rotation.x = rx;
  m.castShadow = true;
  g.add(m);
  return m;
}

// Each model: origin at the palm, barrel along -Z, top along +Y.
function buildModel(key) {
  const g = new THREE.Group();
  const p = {};
  if (key === 'pistol') {
    box(g, 0.03, 0.11, 0.045, 0, -0.02, 0.012, mats.dark, 0.25);
    box(g, 0.032, 0.036, 0.19, 0, 0.055, -0.055, mats.metal);
    box(g, 0.026, 0.02, 0.06, 0, 0.03, -0.03, mats.dark); // trigger guard
    box(g, 0.006, 0.012, 0.006, 0, 0.078, -0.14, mats.sight);
    box(g, 0.022, 0.01, 0.006, 0, 0.077, 0.035, mats.sight);
    p.mag = box(g, 0.024, 0.1, 0.035, 0, -0.03, 0.014, mats.metal, 0.25);
    p.muzzle = new THREE.Vector3(0, 0.055, -0.155);
    p.magwell = new THREE.Vector3(0, -0.08, 0.03);
    p.port = new THREE.Vector3(0.02, 0.07, -0.03);
  } else if (key === 'smg') {
    box(g, 0.03, 0.1, 0.045, 0, -0.02, 0.012, mats.dark, 0.2);
    box(g, 0.042, 0.07, 0.34, 0, 0.055, -0.07, mats.metal);
    box(g, 0.02, 0.02, 0.08, 0, 0.055, -0.27, mats.dark);
    box(g, 0.03, 0.05, 0.18, 0, 0.04, 0.18, mats.dark);
    box(g, 0.028, 0.08, 0.035, 0, -0.03, -0.2, mats.dark); // foregrip
    box(g, 0.006, 0.02, 0.006, 0, 0.1, -0.21, mats.sight);
    box(g, 0.022, 0.012, 0.006, 0, 0.097, 0.05, mats.sight);
    p.mag = box(g, 0.026, 0.16, 0.04, 0, -0.04, -0.1, mats.metal, 0.12);
    p.muzzle = new THREE.Vector3(0, 0.055, -0.315);
    p.magwell = new THREE.Vector3(0, -0.12, -0.09);
    p.port = new THREE.Vector3(0.03, 0.07, -0.08);
  } else {
    box(g, 0.035, 0.11, 0.05, 0, -0.03, 0.02, mats.wood, 0.3);
    box(g, 0.05, 0.08, 0.3, 0, 0.05, -0.08, mats.metal);
    const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.5, 10), mats.metal);
    barrel.rotation.x = Math.PI / 2; barrel.position.set(0, 0.075, -0.47); g.add(barrel);
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.42, 8), mats.dark);
    tube.rotation.x = Math.PI / 2; tube.position.set(0, 0.045, -0.43); g.add(tube);
    box(g, 0.05, 0.045, 0.16, 0, 0.04, -0.4, mats.wood); // pump
    box(g, 0.042, 0.09, 0.3, 0, 0.02, 0.24, mats.wood, -0.08); // stock
    box(g, 0.008, 0.01, 0.008, 0, 0.093, -0.7, mats.sight);
    p.mag = null;
    p.muzzle = new THREE.Vector3(0, 0.075, -0.725);
    p.magwell = new THREE.Vector3(0, 0.0, -0.12);
    p.port = new THREE.Vector3(0.03, 0.07, -0.12);
  }
  return { group: g, points: p };
}

// Common grabbable item behaviour.
class Item {
  constructor(mesh, mass) {
    this.mesh = mesh;
    this.mass = mass;
    this.holder = null;
    this.slot = null;
    this.support = null;
    state.scene.add(mesh);
    // Measure the model in its own frame for the collision box.
    const pos0 = mesh.position.clone(), quat0 = mesh.quaternion.clone();
    mesh.position.set(0, 0, 0);
    mesh.quaternion.identity();
    mesh.updateMatrixWorld(true);
    const bb = new THREE.Box3().setFromObject(mesh);
    mesh.position.copy(pos0);
    mesh.quaternion.copy(quat0);
    const size = bb.getSize(new THREE.Vector3());
    const center = bb.getCenter(new THREE.Vector3());
    this.body = new CANNON.Body({ mass, material: materials.prop, collisionFilterGroup: G.PROP,
      collisionFilterMask: G.WORLD | G.PROP | G.HAND | G.NPC });
    this.body.addShape(new CANNON.Box(new CANNON.Vec3(size.x / 2, size.y / 2, size.z / 2)),
      new CANNON.Vec3(center.x, center.y, center.z));
    this.body.linearDamping = 0.05;
    this.body.angularDamping = 0.15;
    world.addBody(this.body);
    link(this.body, mesh);
    this.body.userData.item = this;
    state.grabbables.add(this.body);
    this.gripLocal = new THREE.Vector3();
    let last = 0;
    this.body.addEventListener('collide', (e) => {
      const v = Math.abs(e.contact.getImpactVelocityAlongNormal());
      if (v > 1.2 && state.time - last > 0.1) { last = state.time; play('impact', this.body.position, Math.min(0.6, v / 8), 1.4); }
    });
  }

  gripWorld(out) { return out.copy(this.gripLocal).applyQuaternion(this.body.quaternion).add(this.body.position); }

  toKinematic(mask) {
    const b = this.body;
    b.type = CANNON.Body.KINEMATIC;
    b.mass = 0;
    b.updateMassProperties();
    b.collisionFilterGroup = G.HELD;
    b.collisionFilterMask = mask;
    b.wakeUp();
  }
  toDynamic() {
    const b = this.body;
    b.type = CANNON.Body.DYNAMIC;
    b.mass = this.mass;
    b.updateMassProperties();
    b.collisionFilterGroup = G.PROP;
    b.collisionFilterMask = G.WORLD | G.PROP | G.HAND | G.NPC;
    b.wakeUp();
  }

  onGrab(hand) {
    this.holder = hand;
    this.toKinematic(G.PROP | G.NPC);
    this.lifetime = Infinity;
  }
  onRelease(hand, velocity) {
    this.holder = null;
    if (this.support) { this.support.held = null; this.support = null; }
    this.toDynamic();
    if (velocity) {
      this.body.velocity.set(velocity.x, velocity.y, velocity.z);
      this.body.angularVelocity.set(Math.random() * 4 - 2, Math.random() * 4 - 2, Math.random() * 4 - 2);
    }
  }
  holsterTo(slot) {
    this.slot = slot;
    slot.item = this;
    this.toKinematic(0);
  }

  // Desired world pose while held or holstered.
  heldPose(h, pos, quat) {
    const hand = this.holder;
    pos.copy(hand.body.position).addScaledVector(toThree(hand.body.velocity, _tmp), h);
    quat.copy(hand.target.quat);
    if (hand.body.position.distanceTo(hand.target.pos) > 0.06) quat.copy(hand.body.quaternion);
  }

  preStep(h) {
    if (this.holder) {
      this.heldPose(h, _p, _q);
      driveToPose(this.body, _p, _q, h, 40);
    } else if (this.slot) {
      this.slot.obj.getWorldPosition(_p);
      this.slot.obj.getWorldQuaternion(_q);
      if (this.slot.name === 'back') _q.multiply(_qBack);
      else _q.multiply(_qHip);
      // Hang the item so its grip sits at the slot.
      _p.sub(_tmp.copy(this.gripLocal).applyQuaternion(_q));
      if (this.body.position.distanceTo(_p) > 0.5) setPose(this.body, _p, _q);
      else driveToPose(this.body, _p, _q, h, 40);
    }
  }
}
const _p = new THREE.Vector3(), _q = new THREE.Quaternion(), _tmp = new THREE.Vector3();
const _qHip = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2 + 0.2, 0, 0));
const _qBack = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2 - 0.4, 0, Math.PI / 2 + 0.6, 'ZXY'));

export class Weapon extends Item {
  constructor(key, pos, quat = new THREE.Quaternion()) {
    const def = DEFS[key];
    const { group, points } = buildModel(key);
    group.position.copy(pos);
    group.quaternion.copy(quat);
    super(group, def.mass);
    this.isWeapon = true;
    this.def = def;
    this.points = points;
    this.ammo = def.cap;
    this.hasMag = def.feed === 'mag';
    this.cooldown = 0;
    this.lastTrigger = false;
    setPose(this.body, pos, quat);
    state.weapons.push(this);
  }

  destroy() {
    if (this.holder) this.holder.dropHeld(false);
    if (this.slot) { this.slot.item = null; this.slot = null; }
    state.grabbables.delete(this.body);
    unlink(this.body);
    world.removeBody(this.body);
    this.mesh.removeFromParent();
    state.weapons.splice(state.weapons.indexOf(this), 1);
  }

  foregripWorld(out) { return out.copy(this.def.foregrip).applyQuaternion(this.body.quaternion).add(this.body.position); }
  worldPoint(local, out) { return out.copy(local).applyQuaternion(this.body.quaternion).add(this.body.position); }

  heldPose(h, pos, quat) {
    super.heldPose(h, pos, quat);
    // Two-handed: aim from the primary grip toward the supporting hand.
    if (this.support && this.def.foregrip) {
      const fg = _tmp.copy(this.def.foregrip).normalize();
      const d1 = fg.applyQuaternion(quat);
      const d2 = new THREE.Vector3().subVectors(this.support.target.pos, pos).normalize();
      quat.premultiply(new THREE.Quaternion().setFromUnitVectors(d1, d2));
    }
  }

  setMagVisible() { if (this.points.mag) this.points.mag.visible = this.hasMag; }

  // Per frame: handle trigger from the holding hand.
  updateWeapon(dt) {
    this.cooldown -= dt;
    const hand = this.holder;
    if (!hand) { this.lastTrigger = false; return; }
    const pulled = hand.triggerDown;
    const fresh = pulled && !this.lastTrigger;
    this.lastTrigger = pulled;
    if (pulled && (fresh || this.def.auto) && this.cooldown <= 0) {
      this.cooldown = 60 / this.def.rpm;
      if (this.ammo > 0 && (this.hasMag || this.def.feed !== 'mag')) this.fire();
      else if (fresh) { play('click', this.body.position, 0.6); hand.pulse(0.1, 15); }
    }
    // Eject magazine with A / X.
    if (hand.edge('a', hand.buttons.a) === 1 && this.def.feed === 'mag' && this.hasMag) this.ejectMag();
  }

  fire() {
    this.ammo--;
    const def = this.def;
    const muzzle = this.worldPoint(this.points.muzzle, new THREE.Vector3());
    const q = this.body.quaternion;
    const tq = new THREE.Quaternion(q.x, q.y, q.z, q.w);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(tq);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(tq);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(tq);

    for (let i = 0; i < def.pellets; i++) {
      const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * def.spread;
      const dir = fwd.clone().addScaledVector(up, Math.sin(a) * r).addScaledVector(right, Math.cos(a) * r).normalize();
      shootRay(muzzle, dir, def.damage, def.impulse, i === 0 || def.pellets < 4 || Math.random() < 0.3);
    }

    muzzleFlash(muzzle, tq);
    play(def.sound, muzzle, 1);
    const two = this.support ? 0.45 : 1;
    this.holder.addRecoil(def.recoil[0] * two, def.recoil[1] * two);
    this.holder.pulse(def.pellets > 1 ? 1 : 0.7, def.pellets > 1 ? 90 : 40);
    if (this.support) this.support.pulse(0.5, 40);
    ejectCasing(this.worldPoint(this.points.port, new THREE.Vector3()), right, up, this.holder.velocity, def.key === 'shotgun');
    state.game.noise(muzzle);
  }

  ejectMag() {
    const pos = this.worldPoint(this.points.magwell, new THREE.Vector3());
    const ammo = new Ammo(this.def.key, pos, this.mesh.quaternion, this.ammo);
    ammo.body.velocity.set(this.holder.velocity.x, this.holder.velocity.y - 1, this.holder.velocity.z);
    this.ammo = 0;
    this.hasMag = false;
    this.setMagVisible();
    play('magIn', pos, 0.5, 0.7);
    this.holder.pulse(0.3, 30);
  }

  // Desktop / instant reload.
  instantReload() {
    this.ammo = this.def.cap;
    this.hasMag = this.def.feed === 'mag';
    this.setMagVisible();
    play('magIn', this.body.position, 0.8);
  }
}

// Magazines and shotgun shells.
const ammoItems = [];
export class Ammo extends Item {
  constructor(key, pos, quat, count) {
    const g = new THREE.Group();
    if (key === 'shotgun') {
      const s = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.065, 8), mats.shell);
      s.rotation.x = Math.PI / 2; g.add(s);
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.012, 8), mats.brass);
      cap.rotation.x = Math.PI / 2; cap.position.z = 0.032; g.add(cap);
    } else {
      const h = key === 'smg' ? 0.16 : 0.1;
      box(g, key === 'smg' ? 0.026 : 0.024, h, key === 'smg' ? 0.04 : 0.035, 0, -h / 2 + 0.01, 0, mats.metal);
      box(g, 0.01, 0.006, 0.02, 0, 0.012, 0, mats.brass);
    }
    g.position.copy(pos);
    g.quaternion.copy(quat);
    super(g, 0.2);
    this.key = key;
    this.count = key === 'shotgun' ? 1 : count;
    this.lifetime = 25;
    setPose(this.body, pos, quat);
    ammoItems.push(this);
    while (ammoItems.length > 14) {
      const old = ammoItems.find((a) => !a.holder);
      if (!old) break;
      old.destroy();
    }
  }
  destroy() {
    if (this.holder) this.holder.held = null;
    state.grabbables.delete(this.body);
    unlink(this.body);
    world.removeBody(this.body);
    this.mesh.removeFromParent();
    const i = ammoItems.indexOf(this);
    if (i >= 0) ammoItems.splice(i, 1);
  }
}

export function spawnAmmoInHand(key, hand) {
  const a = new Ammo(key, hand.body.position, hand.target.quat, DEFS[key].cap);
  play('click', hand.body.position, 0.4, 1.3);
  return a;
}

// Bullet ray: damage NPCs, push rigid bodies, leave marks.
export function shootRay(from, dir, damage, impulse, showTracer) {
  const to = from.clone().addScaledVector(dir, 120);
  const hit = raycast(from, to, G.WORLD | G.PROP | G.NPC);
  if (!hit) { if (showTracer) tracer(from, to); return; }
  if (showTracer) tracer(from, hit.point);
  const b = hit.body;
  const part = b.userData && b.userData.npcPart;
  if (part) {
    part.npc.hit(part, damage, hit.point, dir, impulse);
    burst(hit.point, hit.normal, 'hit', 8, 1.5);
    play('flesh', hit.point, 0.8);
  } else {
    burst(hit.point, hit.normal, b.type === CANNON.Body.STATIC ? 'dust' : 'spark', 8, 2.5);
    play('impact', hit.point, 0.4, 1.6);
    bulletHole(hit.point, hit.normal, b.userData && b.userData.mesh ? b.userData.mesh : null);
    if (b.type === CANNON.Body.DYNAMIC) {
      const rel = new CANNON.Vec3(hit.point.x - b.position.x, hit.point.y - b.position.y, hit.point.z - b.position.z);
      b.applyImpulse(new CANNON.Vec3(dir.x * impulse, dir.y * impulse, dir.z * impulse), rel);
    }
  }
}

// Spent casings: small rigid bodies that bounce off the world.
const casings = [];
let casingIndex = 0;
function ejectCasing(pos, right, up, handVel, shell) {
  let c = casings[casingIndex];
  if (!c) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.02, 6), mats.brass);
    state.scene.add(mesh);
    const body = new CANNON.Body({ mass: 0.01, collisionFilterGroup: G.CASING, collisionFilterMask: G.WORLD });
    body.addShape(new CANNON.Box(new CANNON.Vec3(0.005, 0.01, 0.005)));
    body.linearDamping = 0.1;
    body.allowSleep = true;
    world.addBody(body);
    link(body, mesh);
    let last = 0;
    body.addEventListener('collide', () => { if (state.time - last > 0.3) { last = state.time; play('tink', body.position, 0.25); } });
    c = casings[casingIndex] = { mesh, body };
  }
  casingIndex = (casingIndex + 1) % 30;
  c.mesh.material = shell ? mats.shell : mats.brass;
  c.mesh.scale.set(shell ? 2.2 : 1, shell ? 3 : 1, shell ? 2.2 : 1);
  setPose(c.body, pos, new THREE.Quaternion());
  const s = 1.5 + Math.random();
  c.body.velocity.set(handVel.x + right.x * s + up.x * 1.5, handVel.y + right.y * s + up.y * 1.5, handVel.z + right.z * s + up.z * 1.5);
  c.body.angularVelocity.set(Math.random() * 20, Math.random() * 20, Math.random() * 20);
  c.body.wakeUp();
}

// Before each physics step: drive held / holstered items.
export function itemsPreStep(h) {
  for (const w of state.weapons) w.preStep(h);
  for (const a of ammoItems) a.preStep(h);
}

// Per frame: triggers, reload-by-hand, cleanup.
export function updateItems(dt) {
  for (const w of state.weapons) { w.updateWeapon(dt); w.setMagVisible(); }
  for (const a of [...ammoItems]) {
    if (!a.holder) {
      a.lifetime -= dt;
      if (a.lifetime <= 0 || a.body.position.y < -5) { a.destroy(); continue; }
      continue;
    }
    // Push the held magazine / shell into a matching weapon.
    for (const w of state.weapons) {
      if (w.def.key !== a.key) continue;
      const well = w.worldPoint(w.points.magwell, new THREE.Vector3());
      if (well.distanceTo(a.body.position) > 0.08) continue;
      if (w.def.feed === 'mag' && !w.hasMag) {
        w.hasMag = true;
        w.ammo = a.count;
      } else if (w.def.feed === 'shell' && w.ammo < w.def.cap) {
        w.ammo++;
      } else continue;
      play('magIn', well, 0.9);
      a.holder.pulse(0.6, 40);
      if (w.holder) w.holder.pulse(0.6, 40);
      a.destroy();
      break;
    }
  }
}
