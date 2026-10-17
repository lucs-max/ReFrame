// The player: a rigid-body capsule that follows the headset, physical walking with
// momentum and footsteps, an estimated (or tracked) chest with holsters, and procedural legs.
import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { world, G, materials, raycast } from './physics.js';
import { state } from './state.js';
import { play } from './audio.js';

export const SPAWN = new THREE.Vector3(0, 0, 8);
const WALK = 1.7, SPRINT = 3.6, JUMP = 4.0;
const THIGH = 0.46, SHIN = 0.46;

const _v = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _q = new THREE.Quaternion();
const UP = new THREE.Vector3(0, 1, 0);

function wrapAngle(a) {
  while (a > Math.PI) a -= Math.PI * 2;
  while (a < -Math.PI) a += Math.PI * 2;
  return a;
}
function yawOf(dir) { return Math.atan2(-dir.x, -dir.z); } // yaw where 0 faces -Z

function limbMesh(radius, color) {
  const g = new THREE.CylinderGeometry(radius, radius * 0.85, 1, 8);
  g.translate(0, 0.5, 0);
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, roughness: 0.8 }));
  m.castShadow = true;
  return m;
}
function placeLimb(mesh, a, b) {
  _v.subVectors(b, a);
  const len = _v.length();
  mesh.position.copy(a);
  mesh.quaternion.setFromUnitVectors(UP, _v.divideScalar(len || 1));
  mesh.scale.set(1, len, 1);
}

export class Player {
  constructor() {
    const { scene, rig } = state;
    this.rig = rig;
    this.body = new CANNON.Body({ mass: 70, material: materials.player, fixedRotation: true,
      collisionFilterGroup: G.PLAYER, collisionFilterMask: G.WORLD | G.PROP | G.NPC });
    this.body.addShape(new CANNON.Sphere(0.22), new CANNON.Vec3(0, 0.22, 0));
    this.body.addShape(new CANNON.Sphere(0.22), new CANNON.Vec3(0, 0.75, 0));
    this.body.allowSleep = false;
    this.body.linearDamping = 0;
    world.addBody(this.body);

    this.headLocal = new THREE.Vector3(0, 1.7, 0);
    this.headLocalQuat = new THREE.Quaternion();
    this.headWorld = new THREE.Vector3();
    this.headQuat = new THREE.Quaternion();
    this.chestTracked = null; // {pos, quat} in rig space when body tracking is available

    this.moveVel = new THREE.Vector2(); // smoothed locomotion velocity (world xz)
    this.input = { move: new THREE.Vector2(), sprint: false, jump: false };
    this.grounded = false;
    this.jumpCooldown = 0;
    this.locomotion = 'stick'; // or 'swing'
    this.swingSpeed = 0;

    this.hp = 100;
    this.lastHit = -10;
    this.dead = false;
    this.deadTimer = 0;
    this.hurtFlash = 0;

    // Torso frame (world space, yaw only) at chest height. Holsters and pouches hang off it.
    this.torsoYaw = 0;
    this.torso = new THREE.Group();
    scene.add(this.torso);
    const torsoMat = new THREE.MeshStandardMaterial({ color: 0x3b4a3f, roughness: 0.9 });
    const chestMesh = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.42, 0.18), torsoMat);
    chestMesh.position.set(0, -0.2, 0.06);
    chestMesh.castShadow = true;
    this.torso.add(chestMesh);
    const belt = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.06, 0.2), new THREE.MeshStandardMaterial({ color: 0x2a2018 }));
    belt.position.set(0, -0.44, 0.06);
    this.torso.add(belt);

    this.slots = [];
    const slot = (name, accepts, x, y, z) => {
      const o = new THREE.Object3D();
      o.position.set(x, y, z);
      this.torso.add(o);
      const mark = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.1, 0.05),
        new THREE.MeshStandardMaterial({ color: 0x1e1e1e }));
      mark.position.set(0, -0.06, 0);
      o.add(mark);
      const s = { name, accepts, obj: o, item: null, pos: new THREE.Vector3() };
      this.slots.push(s);
      return s;
    };
    slot('right hip', ['hip'], 0.22, -0.42, 0.04);
    slot('left hip', ['hip'], -0.22, -0.42, 0.04);
    slot('back', ['back'], 0.12, 0.08, 0.2);
    this.pouches = [];
    for (const x of [-0.07, 0.07]) {
      const o = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 0.04), new THREE.MeshStandardMaterial({ color: 0x4d3b2a }));
      o.position.set(x, -0.42, -0.08);
      this.torso.add(o);
      this.pouches.push(o);
    }

    // Legs
    const legColor = 0x2b3340;
    this.legs = ['left', 'right'].map((side, i) => {
      const thigh = limbMesh(0.065, legColor);
      const shin = limbMesh(0.055, legColor);
      const foot = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.07, 0.24), new THREE.MeshStandardMaterial({ color: 0x1b1b1b }));
      foot.castShadow = true;
      scene.add(thigh, shin, foot);
      return {
        side: i === 0 ? -1 : 1, thigh, shin, foot,
        planted: new THREE.Vector3(), from: new THREE.Vector3(), to: new THREE.Vector3(),
        pos: new THREE.Vector3(), t: 1, stepping: false,
      };
    });
    this.hips = new THREE.Vector3();

    // Screen overlay for damage / head-in-wall fade.
    this.overlay = new THREE.Mesh(new THREE.PlaneGeometry(2, 2),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0, depthTest: false, depthWrite: false }));
    this.overlay.position.z = -0.12;
    this.overlay.renderOrder = 999;
    this.overlay.visible = false;
    state.camera.add(this.overlay);

    this.respawn();
  }

  respawn() {
    this.body.position.set(SPAWN.x, SPAWN.y + 0.05, SPAWN.z);
    this.body.velocity.set(0, 0, 0);
    this.moveVel.set(0, 0);
    this.rig.rotation.set(0, 0, 0);
    this.rig.position.set(SPAWN.x, SPAWN.y, SPAWN.z);
    this.rig.updateMatrixWorld();
    this.syncRig();
    this.hp = 100;
    this.dead = false;
    for (const l of this.legs) l.t = 1;
    this.resetLegs = true;
  }

  setHead(pos, quat) {
    this.headLocal.copy(pos);
    this.headLocalQuat.copy(quat);
  }

  computeHeadWorld() {
    this.rig.updateMatrixWorld();
    this.headWorld.copy(this.headLocal).applyMatrix4(this.rig.matrixWorld);
    this.rig.getWorldQuaternion(_q);
    this.headQuat.copy(_q).multiply(this.headLocalQuat);
  }

  headYaw() {
    _v.set(0, 0, -1).applyQuaternion(this.headQuat);
    if (Math.abs(_v.y) > 0.95) _v.set(0, 1, 0).applyQuaternion(this.headQuat).multiplyScalar(-Math.sign(_v.y) || 1);
    return yawOf(_v);
  }

  snapTurn(angle) {
    this.computeHeadWorld();
    const pivot = this.headWorld;
    _v.subVectors(this.rig.position, pivot).applyAxisAngle(UP, angle);
    this.rig.position.copy(pivot).add(_v);
    this.rig.rotation.y += angle;
    this.rig.updateMatrixWorld();
  }

  // Called before each physics step.
  preStep(h) {
    this.computeHeadWorld();
    const b = this.body;

    // Ground check
    const from = _v.set(b.position.x, b.position.y + 0.3, b.position.z);
    const to = _v2.set(b.position.x, b.position.y - 0.08, b.position.z);
    const hit = raycast(from, to, G.WORLD | G.PROP);
    this.grounded = !!hit;
    this.jumpCooldown -= h;

    // Desired locomotion velocity
    let speed = 0;
    const dir = new THREE.Vector2();
    const yaw = this.headYaw();
    if (this.dead) {
      speed = 0;
    } else if (this.locomotion === 'swing' && this.input.move.lengthSq() < 0.01) {
      speed = this.swingSpeed;
      dir.set(-Math.sin(yaw), -Math.cos(yaw));
    } else {
      const m = this.input.move;
      const mag = Math.min(1, m.length());
      if (mag > 0.1) {
        speed = mag * (this.input.sprint ? SPRINT : WALK);
        // stick y forward is negative on gamepads; m.y is already "forward = +"
        const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
        const rx = Math.cos(yaw), rz = -Math.sin(yaw);
        dir.set(fx * m.y + rx * m.x, fz * m.y + rz * m.x).normalize();
      }
    }
    const target = dir.multiplyScalar(speed);
    const accel = this.grounded ? (speed > 0 ? 9 : 14) : 2.5;
    const dv = _v2.set(target.x - this.moveVel.x, 0, target.y - this.moveVel.y);
    const maxDv = accel * h;
    if (dv.length() > maxDv) dv.setLength(maxDv);
    this.moveVel.x += dv.x;
    this.moveVel.y += dv.z;

    // Locomotion carries the tracking origin; the body then follows the head.
    if (!this.dead) {
      this.rig.position.x += this.moveVel.x * h;
      this.rig.position.z += this.moveVel.y * h;
      this.computeHeadWorld();
    }
    let fx = (this.headWorld.x - b.position.x) / h * 0.6;
    let fz = (this.headWorld.z - b.position.z) / h * 0.6;
    const fl = Math.hypot(fx, fz);
    const maxFollow = 6;
    if (fl > maxFollow) { fx *= maxFollow / fl; fz *= maxFollow / fl; }
    b.velocity.x = fx;
    b.velocity.z = fz;
    if (this.grounded && this.input.jump && this.jumpCooldown <= 0 && !this.dead) {
      b.velocity.y = JUMP;
      this.jumpCooldown = 0.4;
    }
  }

  // Called after each physics step: keep the head attached to the body. The head may lean
  // up to LEAN past the body (over low cover), but never into walls.
  syncRig() {
    this.computeHeadWorld();
    const b = this.body;
    const LEAN = 0.45;
    let ox = this.headWorld.x - b.position.x, oz = this.headWorld.z - b.position.z;
    const ol = Math.hypot(ox, oz);
    if (ol > LEAN) {
      const k = 1 - LEAN / ol;
      this.rig.position.x -= ox * k;
      this.rig.position.z -= oz * k;
    }
    this.rig.position.y = b.position.y;
    this.rig.updateMatrixWorld();
    this.computeHeadWorld();

    // Head collision: a 12 cm sphere swept from above the body to the head.
    ox = this.headWorld.x - b.position.x; oz = this.headWorld.z - b.position.z;
    const d = Math.hypot(ox, oz);
    if (d > 0.01) {
      const dx = ox / d, dz = oz / d;
      const from = _v.set(b.position.x, this.headWorld.y, b.position.z);
      const to = _v2.set(this.headWorld.x + dx * 0.12, this.headWorld.y, this.headWorld.z + dz * 0.12);
      const hit = raycast(from, to, G.WORLD);
      if (hit) {
        const push = d + 0.12 - hit.distance;
        this.rig.position.x -= dx * push;
        this.rig.position.z -= dz * push;
        this.rig.updateMatrixWorld();
        this.computeHeadWorld();
      }
    }
  }

  // Arm-swing locomotion: hands moving in opposite vertical directions walk you forward.
  updateSwing(dt, leftVelY, rightVelY) {
    let target = 0;
    if (leftVelY * rightVelY < 0) target = Math.min(SPRINT, (Math.abs(leftVelY) + Math.abs(rightVelY)) * 1.4);
    const k = target > this.swingSpeed ? 6 : 2.5;
    this.swingSpeed += (target - this.swingSpeed) * Math.min(1, k * dt);
  }

  update(dt) {
    this.computeHeadWorld();
    const head = this.headWorld;

    // Chest: from body tracking when available, otherwise estimated from head and hands.
    const neck = _v.set(0, -0.09, 0.08).applyQuaternion(this.headQuat).add(head);
    let chestPos = neck.clone().add(_v2.set(0, -0.2, 0));
    const headYaw = this.headYaw();
    if (this.chestTracked) {
      chestPos = this.chestTracked.pos.clone().applyMatrix4(this.rig.matrixWorld);
      this.rig.getWorldQuaternion(_q);
      _q.multiply(this.chestTracked.quat);
      this.torsoYaw = yawOf(_v2.set(0, 0, -1).applyQuaternion(_q));
    } else {
      let target = headYaw;
      const hs = state.hands;
      if (hs.length === 2 && hs[0].tracked && hs[1].tracked) {
        const mid = _v2.copy(hs[0].target.pos).add(hs[1].target.pos).multiplyScalar(0.5).sub(neck);
        mid.y = 0;
        if (mid.length() > 0.15) {
          const handsYaw = yawOf(mid);
          const d = wrapAngle(handsYaw - headYaw);
          if (Math.abs(d) < 1.6) target = headYaw + d * 0.4;
        }
      }
      let diff = wrapAngle(target - this.torsoYaw);
      this.torsoYaw += diff * Math.min(1, dt * 3);
      const lim = 0.85; // the head can turn this far before the body follows
      diff = wrapAngle(headYaw - this.torsoYaw);
      if (diff > lim) this.torsoYaw = headYaw - lim;
      if (diff < -lim) this.torsoYaw = headYaw + lim;
    }
    this.torso.position.copy(chestPos);
    this.torso.rotation.set(0, this.torsoYaw, 0);
    this.torso.updateMatrixWorld();
    for (const s of this.slots) s.obj.getWorldPosition(s.pos);

    this.updateLegs(dt);
    this.updateHealth(dt);
  }

  pouchDistance(p) {
    let best = Infinity;
    for (const o of this.pouches) best = Math.min(best, o.getWorldPosition(_v).distanceTo(p));
    return best;
  }

  freeSlotNear(p, holsterType, r = 0.22) {
    let best = null, bd = r;
    for (const s of this.slots) {
      if (s.item || !s.accepts.includes(holsterType)) continue;
      const d = s.pos.distanceTo(p);
      if (d < bd) { bd = d; best = s; }
    }
    return best;
  }

  updateLegs(dt) {
    const b = this.body;
    const fwd = _v.set(-Math.sin(this.torsoYaw), 0, -Math.cos(this.torsoYaw));
    const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
    const ground = b.position.y;
    const legLen = THIGH + SHIN;
    // Hips sit under the chest; they drop when you crouch for real.
    this.hips.copy(this.torso.position).addScaledVector(fwd, -0.02);
    this.hips.y = Math.min(this.torso.position.y - 0.45, ground + legLen - 0.02);
    const vel = new THREE.Vector3(b.velocity.x, 0, b.velocity.z);
    const speed = vel.length();

    for (const leg of this.legs) {
      const rest = this.hips.clone().addScaledVector(right, leg.side * 0.11).addScaledVector(vel, 0.18);
      rest.y = ground;
      const g = raycast(_v2.set(rest.x, ground + 0.5, rest.z), new THREE.Vector3(rest.x, ground - 0.4, rest.z), G.WORLD | G.PROP);
      if (g) rest.y = g.point.y;
      if (this.resetLegs) { leg.planted.copy(rest); leg.pos.copy(rest); leg.t = 1; leg.stepping = false; }
      leg.rest = rest;
    }
    this.resetLegs = false;

    const stride = 0.22 + speed * 0.1;
    const other = (l) => this.legs[l === this.legs[0] ? 1 : 0];
    for (const leg of this.legs) {
      if (leg.stepping) {
        leg.t += dt / (0.32 / (1 + speed * 0.35));
        leg.to.copy(leg.rest);
        const t = Math.min(1, leg.t);
        leg.pos.lerpVectors(leg.from, leg.to, t);
        leg.pos.y += Math.sin(t * Math.PI) * (0.06 + speed * 0.02);
        if (t >= 1) {
          leg.stepping = false;
          leg.planted.copy(leg.to);
          if (this.grounded) play('step', leg.planted, 0.25 + Math.min(speed, 4) * 0.12, 0.9 + Math.random() * 0.2);
        }
      } else {
        leg.pos.copy(leg.planted);
        const d = Math.hypot(leg.planted.x - leg.rest.x, leg.planted.z - leg.rest.z);
        if ((d > stride || Math.abs(leg.planted.y - leg.rest.y) > 0.25) && !other(leg).stepping) {
          leg.stepping = true;
          leg.t = 0;
          leg.from.copy(leg.planted);
        }
      }
      if (!this.grounded) { leg.pos.copy(leg.rest); leg.pos.y = Math.max(ground, this.hips.y - legLen * 0.95); leg.planted.copy(leg.pos); }

      // Two-bone IK
      const hip = this.hips.clone().addScaledVector(right, leg.side * 0.1);
      const footTarget = leg.pos.clone().add(new THREE.Vector3(0, 0.06, 0));
      const toFoot = footTarget.clone().sub(hip);
      let d = toFoot.length();
      const dirN = toFoot.clone().divideScalar(d || 1);
      d = Math.min(d, legLen - 0.001);
      const cosA = (THIGH * THIGH + d * d - SHIN * SHIN) / (2 * THIGH * d);
      const a = Math.acos(THREE.MathUtils.clamp(cosA, -1, 1));
      const bend = fwd.clone().addScaledVector(dirN, -fwd.dot(dirN)).normalize();
      const knee = hip.clone().addScaledVector(dirN, Math.cos(a) * THIGH).addScaledVector(bend, Math.sin(a) * THIGH);
      const foot = hip.clone().addScaledVector(dirN, d);
      placeLimb(leg.thigh, hip, knee);
      placeLimb(leg.shin, knee, foot);
      leg.foot.position.copy(foot).addScaledVector(fwd, 0.05);
      leg.foot.position.y -= 0.03;
      leg.foot.rotation.set(0, this.torsoYaw, 0);
    }
  }

  // Damage from an enemy. Returns true if it landed.
  damage(amount) {
    if (this.dead || !state.game.hostile) return false;
    this.hp -= amount;
    this.lastHit = state.time;
    this.hurtFlash = Math.min(0.75, this.hurtFlash + 0.45);
    play('hurt', null, 0.7);
    for (const h of state.hands) h.pulse(0.6, 80);
    if (this.hp <= 0) {
      this.hp = 0;
      this.dead = true;
      this.deadTimer = 3;
      state.game.onPlayerDeath();
    }
    return true;
  }

  // Hit test of a bullet segment against the head and torso. Returns 'head', 'body', 'legs' or null.
  hitTest(a, b) {
    if (segSphere(a, b, this.headWorld, 0.13)) return 'head';
    // Torso as an oriented box in torso space.
    this.torso.updateMatrixWorld();
    const inv = new THREE.Matrix4().copy(this.torso.matrixWorld).invert();
    const la = a.clone().applyMatrix4(inv), lb = b.clone().applyMatrix4(inv);
    if (segBox(la, lb, new THREE.Vector3(-0.19, -0.5, -0.07), new THREE.Vector3(0.19, 0.02, 0.17))) return 'body';
    for (const leg of this.legs) {
      if (segSphere(a, b, leg.thigh.position.clone().lerp(leg.foot.position, 0.5), 0.15)) return 'legs';
    }
    return null;
  }

  updateHealth(dt) {
    if (this.dead) {
      this.deadTimer -= dt;
      if (this.deadTimer <= 0) { this.respawn(); state.game.onPlayerRespawn(); }
    } else if (state.time - this.lastHit > 4 && this.hp < 100) {
      this.hp = Math.min(100, this.hp + 12 * dt);
    }
    this.hurtFlash = Math.max(0, this.hurtFlash - dt * 1.2);

    // Fade to black if the head is pushed into a wall (no seeing through geometry).
    const inWall = !!raycast(this.torso.position, this.headWorld, G.WORLD);
    const m = this.overlay.material;
    let opacity = this.hurtFlash;
    let color = 0x8a0000;
    if (!this.dead && this.hp < 40) opacity = Math.max(opacity, (40 - this.hp) / 80);
    if (this.dead) { opacity = 0.85; color = 0x300000; }
    if (inWall) { opacity = 1; color = 0x000000; }
    m.color.setHex(color);
    m.opacity = opacity;
    this.overlay.visible = opacity > 0.01;
  }
}

const _d = new THREE.Vector3(), _w = new THREE.Vector3();
export function segSphere(a, b, c, r) {
  _d.subVectors(b, a);
  const len2 = _d.lengthSq() || 1e-9;
  const t = THREE.MathUtils.clamp(_w.subVectors(c, a).dot(_d) / len2, 0, 1);
  return _w.copy(a).addScaledVector(_d, t).distanceToSquared(c) <= r * r;
}
export function segBox(a, b, min, max) {
  let t0 = 0, t1 = 1;
  for (const k of ['x', 'y', 'z']) {
    const d = b[k] - a[k];
    if (Math.abs(d) < 1e-9) { if (a[k] < min[k] || a[k] > max[k]) return false; continue; }
    let ta = (min[k] - a[k]) / d, tb = (max[k] - a[k]) / d;
    if (ta > tb) [ta, tb] = [tb, ta];
    t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
    if (t0 > t1) return false;
  }
  return true;
}
