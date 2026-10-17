// Enemy soldiers: procedurally animated kinematic bodies while alive, full ragdolls when killed.
import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { world, G, materials, link, unlink, driveToPose, raycast, toThree } from './physics.js';
import { state } from './state.js';
import { play } from './audio.js';
import { burst } from './effects.js';
import { segSphere } from './player.js';
import { ARENA } from './world.js';
import { Weapon } from './weapons.js';

const ALIVE_MASK = G.PROP | G.HAND | G.PLAYER;
const DEAD_MASK = G.WORLD | G.PROP | G.HAND | G.NPC;

const _p = new THREE.Vector3(), _q = new THREE.Quaternion(), _s = new THREE.Vector3();
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3();

const PALETTES = [
  { shirt: 0x8b3a3a, pants: 0x2f3437, skin: 0xc68e64 },
  { shirt: 0x6b6b2f, pants: 0x3a3226, skin: 0x8d5a3b },
  { shirt: 0x34506b, pants: 0x262b30, skin: 0xe0b08a },
  { shirt: 0x5a4a6b, pants: 0x2c2c2c, skin: 0x6e4630 },
];
const matCache = new Map();
function mat(c) {
  if (!matCache.has(c)) matCache.set(c, new THREE.MeshStandardMaterial({ color: c, roughness: 0.85 }));
  return matCache.get(c);
}

function grp(parent, x, y, z) {
  const g = new THREE.Object3D();
  g.position.set(x, y, z);
  parent.add(g);
  return g;
}

let corpses = [];

export class NPC {
  constructor(x, z, level = 1) {
    this.level = level;
    this.hp = 100;
    this.alive = true;
    this.state = 'patrol';
    this.yaw = Math.random() * Math.PI * 2;
    this.speed = 0;
    this.vel = new THREE.Vector3();
    this.phase = Math.random() * 10;
    this.flinch = 0; this.flinchSide = 1;
    this.fireTimer = 1.5 + Math.random() * 2;
    this.windup = 0;
    this.strafeDir = Math.random() < 0.5 ? -1 : 1;
    this.strafeTimer = 2;
    this.seeTimer = 0;
    this.canSee = false;
    this.lastSeen = -100;
    this.lastKnown = new THREE.Vector3();
    this.waypoint = null;
    this.groundY = 0;
    this.knock = new THREE.Vector3();

    // Skeleton (not rendered): drives the kinematic bodies.
    const root = this.root = new THREE.Object3D();
    root.position.set(x, 0, z);
    const pelvis = this.pelvis = grp(root, 0, 0.95, 0);
    const spine = this.spine = grp(pelvis, 0, 0.1, 0);
    const chestA = grp(spine, 0, 0.23, 0);
    const neck = this.neck = grp(spine, 0, 0.42, 0);
    const headA = grp(neck, 0, 0.13, 0);
    const sh = this.shoulders = [-1, 1].map((sx) => grp(spine, sx * 0.24, 0.38, 0));
    const upperA = sh.map((s) => grp(s, 0, -0.15, 0));
    const el = this.elbows = sh.map((s) => grp(s, 0, -0.3, 0));
    const foreA = el.map((e) => grp(e, 0, -0.14, 0));
    const hips = this.hips = [-1, 1].map((sx) => grp(pelvis, sx * 0.1, -0.05, 0));
    const thighA = hips.map((h) => grp(h, 0, -0.21, 0));
    const knees = this.knees = hips.map((h) => grp(h, 0, -0.42, 0));
    const shinA = knees.map((k) => grp(k, 0, -0.22, 0));

    const pal = PALETTES[Math.floor(Math.random() * PALETTES.length)];
    this.parts = [];
    const part = (name, anchor, shape, geo, color, mass, mult) => {
      const body = new CANNON.Body({ mass: 0, type: CANNON.Body.KINEMATIC, material: materials.prop,
        collisionFilterGroup: G.NPC, collisionFilterMask: ALIVE_MASK });
      body.addShape(shape);
      body.allowSleep = false;
      world.addBody(body);
      const mesh = new THREE.Mesh(geo, mat(color));
      mesh.castShadow = true;
      state.scene.add(mesh);
      link(body, mesh);
      const p = { name, anchor, body, mesh, mass, mult, npc: this };
      body.userData.npcPart = p;
      body.userData.npc = this;
      body.addEventListener('collide', (e) => this.onCollide(p, e));
      this.parts.push(p);
      return p;
    };
    const B = (w, h, d) => [new CANNON.Box(new CANNON.Vec3(w / 2, h / 2, d / 2)), new THREE.BoxGeometry(w, h, d)];
    this.P = {};
    this.P.pelvis = part('pelvis', pelvis, ...B(0.32, 0.2, 0.2), pal.pants, 12, 0.9);
    this.P.chest = part('chest', chestA, ...B(0.38, 0.42, 0.22), pal.shirt, 18, 1);
    this.P.head = part('head', headA, new CANNON.Sphere(0.12), new THREE.SphereGeometry(0.12, 14, 10), pal.skin, 5, 3.5);
    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.05, 0.05), mat(0x111111));
    visor.position.set(0, 0.02, 0.1);
    this.P.head.mesh.add(visor);
    const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.13, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), mat(0x3d4a32));
    helmet.position.y = 0.02;
    this.P.head.mesh.add(helmet);
    this.P.upper = [0, 1].map((i) => part('arm', upperA[i], ...B(0.09, 0.3, 0.09), pal.shirt, 2.5, 0.55));
    this.P.fore = [0, 1].map((i) => part('arm', foreA[i], ...B(0.08, 0.28, 0.08), pal.skin, 1.8, 0.5));
    this.P.thigh = [0, 1].map((i) => part('leg', thighA[i], ...B(0.13, 0.42, 0.14), pal.pants, 7, 0.6));
    this.P.shin = [0, 1].map((i) => part('leg', shinA[i], ...B(0.11, 0.44, 0.12), pal.pants, 4, 0.5));

    // A pistol in the right hand (visual only while alive).
    const gun = this.gun = new THREE.Group();
    const gm = new THREE.MeshStandardMaterial({ color: 0x1b1d20, roughness: 0.5 });
    const slide = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.035, 0.18), gm);
    slide.position.set(0, 0.04, -0.05);
    gun.add(slide);
    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.028, 0.09, 0.04), gm);
    gun.add(handle);
    this.glint = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 6), new THREE.MeshBasicMaterial({ color: 0xff3020 }));
    this.glint.position.set(0, 0.04, -0.15);
    this.glint.visible = false;
    gun.add(this.glint);
    gun.position.set(0, -0.17, 0.03);
    // Barrel along the arm, sights facing up when the arm is raised.
    gun.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 1).normalize(), Math.PI);
    this.P.fore[1].mesh.add(gun);
    this.muzzleLocal = new THREE.Vector3(0, 0.04, -0.15);

    this.updateGround(true);
    this.animate(0);
    this.snapBodies();
    state.npcs.push(this);
  }

  snapBodies() {
    this.root.updateMatrixWorld(true);
    for (const p of this.parts) {
      p.anchor.matrixWorld.decompose(_p, _q, _s);
      p.body.position.set(_p.x, _p.y, _p.z);
      p.body.quaternion.set(_q.x, _q.y, _q.z, _q.w);
      p.body.aabbNeedsUpdate = true;
      p.mesh.position.copy(_p);
      p.mesh.quaternion.copy(_q);
    }
  }

  headPos(out) { return toThree(this.P.head.body.position, out); }

  preStep(h) {
    if (!this.alive) return;
    for (const p of this.parts) {
      p.anchor.matrixWorld.decompose(_p, _q, _s);
      driveToPose(p.body, _p, _q, h, 20);
    }
  }

  onCollide(part, e) {
    const other = e.body;
    const v = Math.abs(e.contact.getImpactVelocityAlongNormal());
    if (!this.alive) {
      if (v > 2.5 && state.time - (this.lastThud || 0) > 0.15) { this.lastThud = state.time; play('impact', part.body.position, Math.min(0.7, v / 8), 0.5); }
      return;
    }
    if (other.type !== CANNON.Body.DYNAMIC) return;
    const isHand = (other.collisionFilterGroup & G.HAND) !== 0;
    if (v < (isHand ? 2.2 : 3.5)) return;
    if (state.time - (this.lastBlunt || 0) < 0.2) return;
    this.lastBlunt = state.time;
    const dmg = isHand ? v * 7 : Math.min(120, v * other.mass * 0.6);
    const dir = toThree(other.velocity, new THREE.Vector3()).normalize();
    this.hit(part, dmg / part.mult, toThree(part.body.position, new THREE.Vector3()), dir, Math.min(40, v * other.mass * 0.5));
    play('flesh', part.body.position, 0.8, 0.7);
    if (isHand) for (const hnd of state.hands) if (hnd.body === other) hnd.pulse(0.8, 50);
  }

  hit(part, damage, point, dir, impulse) {
    if (!this.alive) {
      const b = part.body;
      b.applyImpulse(new CANNON.Vec3(dir.x * impulse, dir.y * impulse, dir.z * impulse),
        new CANNON.Vec3(point.x - b.position.x, point.y - b.position.y, point.z - b.position.z));
      return;
    }
    this.hp -= damage * part.mult;
    this.state = 'combat';
    this.lastKnown.copy(state.player.headWorld);
    this.lastSeen = state.time;
    this.flinch = Math.min(0.6, this.flinch + 0.25 + damage * 0.004);
    this.flinchSide = Math.random() < 0.5 ? -1 : 1;
    this.knock.addScaledVector(_v.set(dir.x, 0, dir.z), impulse * 0.03);
    this.windup = 0; this.glint.visible = false;
    this.fireTimer = Math.max(this.fireTimer, 0.5);
    if (this.hp <= 0) this.die(part, point, dir, impulse, part === this.P.head);
  }

  die(part, point, dir, impulse, headshot) {
    this.alive = false;
    this.state = 'dead';
    this.glint.visible = false;
    this.deathTime = state.time;
    state.game.onKill(this, headshot);

    // Drop the gun as a real pickup sometimes.
    this.gun.removeFromParent();
    if (Math.random() < 0.4) {
      const dropped = state.weapons.filter((w) => w.dropped && !w.holder && !w.slot);
      if (dropped.length >= 4) dropped[0].destroy();
      const w = new Weapon('pistol', this.P.fore[1].mesh.localToWorld(new THREE.Vector3(0, -0.2, 0)), this.P.fore[1].mesh.quaternion);
      w.dropped = true;
      w.ammo = 3 + Math.floor(Math.random() * 8);
    }

    // Become a ragdoll: dynamic parts joined by cone-twist joints.
    this.root.updateMatrixWorld(true);
    for (const p of this.parts) {
      const b = p.body;
      b.type = CANNON.Body.DYNAMIC;
      b.mass = p.mass;
      b.updateMassProperties();
      b.collisionFilterMask = DEAD_MASK;
      b.velocity.scale(0.6, b.velocity);
      b.angularVelocity.scale(0.3, b.angularVelocity);
      b.linearDamping = 0.05;
      b.angularDamping = 0.25;
      b.allowSleep = true;
      b.sleepSpeedLimit = 0.2;
      b.sleepTimeLimit = 1;
      state.grabbables.add(b);
    }
    const P = this.P;
    const joint = (a, b, pivotObj, axis, angle, twist) => {
      const pivot = pivotObj.getWorldPosition(new THREE.Vector3());
      const pv = new CANNON.Vec3(pivot.x, pivot.y, pivot.z);
      const axisB = new CANNON.Vec3(...axis);
      const worldAxis = b.body.quaternion.vmult(axisB);
      const c = new CANNON.ConeTwistConstraint(a.body, b.body, {
        pivotA: a.body.pointToLocalFrame(pv), pivotB: b.body.pointToLocalFrame(pv),
        axisA: a.body.vectorToLocalFrame(worldAxis), axisB,
        angle, twistAngle: twist, collideConnected: false, maxForce: 1e5,
      });
      world.addConstraint(c);
      return c;
    };
    this.constraints = [
      joint(P.pelvis, P.chest, this.spine, [0, 1, 0], 0.45, 0.35),
      joint(P.chest, P.head, this.neck, [0, 1, 0], 0.55, 0.6),
    ];
    for (let i = 0; i < 2; i++) {
      this.constraints.push(
        joint(P.chest, P.upper[i], this.shoulders[i], [0, -1, 0], 1.5, 0.6),
        joint(P.upper[i], P.fore[i], this.elbows[i], [0, -1, 0], 1.2, 0.2),
        joint(P.pelvis, P.thigh[i], this.hips[i], [0, -1, 0], 1.0, 0.3),
        joint(P.thigh[i], P.shin[i], this.knees[i], [0, -1, 0], 1.1, 0.1),
      );
    }
    // The killing shot shoves the hit part (and a little of the rest of the body).
    const b = part.body;
    const kick = impulse * (headshot ? 1.6 : 2.2);
    b.applyImpulse(new CANNON.Vec3(dir.x * kick, dir.y * kick + 1, dir.z * kick),
      new CANNON.Vec3(point.x - b.position.x, point.y - b.position.y, point.z - b.position.z));
    P.chest.body.applyImpulse(new CANNON.Vec3(dir.x * impulse, 0, dir.z * impulse), new CANNON.Vec3(0, 0.1, 0));

    corpses.push(this);
    while (corpses.length > 7) corpses[0].remove();
  }

  remove() {
    for (const c of this.constraints || []) world.removeConstraint(c);
    for (const p of this.parts) {
      for (const hand of state.hands) if (hand.held && hand.held.body === p.body) hand.dropHeld(false);
      state.grabbables.delete(p.body);
      unlink(p.body);
      world.removeBody(p.body);
      p.mesh.removeFromParent();
    }
    corpses = corpses.filter((c) => c !== this);
    state.npcs.splice(state.npcs.indexOf(this), 1);
  }

  updateGround(force) {
    const r = this.root.position;
    const hit = raycast(_v.set(r.x, 2.5, r.z), _v2.set(r.x, -0.5, r.z), G.WORLD);
    const y = hit ? hit.point.y : 0;
    this.groundY = force ? y : this.groundY + (y - this.groundY) * 0.3;
  }

  update(dt) {
    if (!this.alive) {
      if (state.time - this.deathTime > 40 && !this.grabbed) this.remove();
      return;
    }
    const player = state.player;
    const game = state.game;
    const target = player.headWorld;
    const head = this.headPos(_v);
    const toP = new THREE.Vector3().subVectors(target, this.root.position);
    toP.y = 0;
    const dist = toP.length();

    // Perception, a few times per second.
    this.seeTimer -= dt;
    if (this.seeTimer <= 0) {
      this.seeTimer = 0.2 + Math.random() * 0.1;
      const blocked = raycast(head, target, G.WORLD | G.PROP);
      this.canSee = !player.dead && !blocked && dist < 35;
      if (this.canSee) {
        this.lastSeen = state.time;
        this.lastKnown.copy(target);
        if (this.state === 'patrol') {
          // Notice the player if they're in front of us or close by.
          const facing = new THREE.Vector3(Math.sin(this.yaw), 0, Math.cos(this.yaw));
          if (facing.dot(toP.clone().normalize()) > 0.2 || dist < 6) this.state = 'combat';
        }
      }
      this.updateGround(false);
    }
    if (player.dead && this.state === 'combat') this.state = 'patrol';

    // Decide where to move.
    const desired = new THREE.Vector3();
    let faceYaw = null;
    if (this.state === 'patrol') {
      if (!this.waypoint || this.root.position.distanceTo(this.waypoint) < 1) {
        this.waypoint = new THREE.Vector3((Math.random() * 2 - 1) * (ARENA - 4), 0, -ARENA + 3 + Math.random() * (ARENA + 2));
      }
      desired.subVectors(this.waypoint, this.root.position).setY(0).setLength(1.1);
    } else {
      faceYaw = Math.atan2(toP.x, toP.z);
      const dirP = toP.clone().normalize();
      const side = new THREE.Vector3(dirP.z, 0, -dirP.x).multiplyScalar(this.strafeDir);
      this.strafeTimer -= dt;
      if (this.strafeTimer <= 0) { this.strafeTimer = 1.5 + Math.random() * 2.5; this.strafeDir *= -1; }
      if (!this.canSee && state.time - this.lastSeen > 1.5) {
        desired.subVectors(this.lastKnown, this.root.position).setY(0);
        if (desired.length() > 1) desired.setLength(2.2); else desired.set(0, 0, 0);
      } else if (dist > 13) desired.copy(dirP).multiplyScalar(2.0).addScaledVector(side, 0.6);
      else if (dist < 5) desired.copy(dirP).multiplyScalar(-1.5).addScaledVector(side, 0.8);
      else desired.copy(side).multiplyScalar(1.3);
      if (this.windup > 0) desired.multiplyScalar(0.2); // plant feet to shoot
    }

    // Avoid obstacles and each other.
    if (desired.lengthSq() > 0.01) {
      const dir = desired.clone().normalize();
      const from = _v2.copy(this.root.position).setY(this.groundY + 0.6);
      if (raycast(from, from.clone().addScaledVector(dir, 1.1), G.WORLD | G.PROP)) {
        const left = dir.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), 1.3);
        const right = dir.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), -1.3);
        const okL = !raycast(from, from.clone().addScaledVector(left, 1.3), G.WORLD | G.PROP);
        desired.copy(okL ? left : right).multiplyScalar(desired.length());
        if (this.state === 'patrol' && !okL) this.waypoint = null;
      }
    }
    for (const o of state.npcs) {
      if (o === this || !o.alive) continue;
      const d = _v2.subVectors(this.root.position, o.root.position).setY(0);
      const l = d.length();
      if (l < 1.2 && l > 0.001) desired.addScaledVector(d.normalize(), (1.2 - l) * 3);
    }

    this.vel.lerp(desired, Math.min(1, dt * 4));
    this.knock.multiplyScalar(Math.max(0, 1 - dt * 6));
    this.root.position.addScaledVector(this.vel, dt).addScaledVector(this.knock, dt);
    const lim = ARENA - 1;
    this.root.position.x = THREE.MathUtils.clamp(this.root.position.x, -lim, lim);
    this.root.position.z = THREE.MathUtils.clamp(this.root.position.z, -lim, lim);
    this.root.position.y = this.groundY;
    this.speed = this.vel.length();

    // Turn toward movement or the player.
    if (faceYaw === null && this.speed > 0.2) faceYaw = Math.atan2(this.vel.x, this.vel.z);
    if (faceYaw !== null) {
      let d = faceYaw - this.yaw;
      while (d > Math.PI) d -= Math.PI * 2;
      while (d < -Math.PI) d += Math.PI * 2;
      this.yaw += THREE.MathUtils.clamp(d, -4 * dt, 4 * dt);
    }

    // Shooting (with a visible wind-up so the player can react).
    if (this.state === 'combat' && this.canSee && game.hostile && !player.dead) {
      this.fireTimer -= dt;
      if (this.windup > 0) {
        this.windup -= dt;
        this.glint.visible = Math.floor(state.time * 20) % 2 === 0;
        if (this.windup <= 0) { this.glint.visible = false; this.shoot(); }
      } else if (this.fireTimer <= 0) {
        this.windup = Math.max(0.25, 0.5 - this.level * 0.03);
      }
    } else {
      this.glint.visible = false;
      this.windup = 0;
    }

    this.animate(dt);
  }

  animate(dt) {
    const s = Math.min(1, this.speed / 2);
    this.phase += dt * (2 + this.speed * 3.2);
    const ph = this.phase;
    this.flinch = Math.max(0, this.flinch - dt * 2);
    this.root.rotation.y = this.yaw;
    this.pelvis.position.y = 0.95 - Math.abs(Math.sin(ph)) * 0.03 * s;
    for (let i = 0; i < 2; i++) {
      const sgn = i === 0 ? 1 : -1;
      const sw = Math.sin(ph + (i ? Math.PI : 0));
      this.hips[i].rotation.x = -sw * 0.55 * s;
      this.knees[i].rotation.x = Math.max(0, Math.cos(ph + (i ? Math.PI : 0))) * 0.9 * s + 0.05;
      this.shoulders[i].rotation.set(sw * 0.4 * s, 0, sgn * -0.08);
      this.elbows[i].rotation.x = -0.25;
    }
    this.spine.rotation.set(this.flinch * 0.6, 0, this.flinch * 0.3 * this.flinchSide);
    this.neck.rotation.set(0, 0, 0);
    if (this.state === 'combat') {
      // Aim the right arm (and twist the torso) at the player.
      this.root.updateMatrixWorld(true);
      const sh = this.shoulders[1].getWorldPosition(_v);
      const t = state.player.torso.position;
      const dx = t.x - sh.x, dy = t.y - 0.05 - sh.y, dz = t.z - sh.z;
      const yawTo = Math.atan2(dx, dz);
      let rel = yawTo - this.yaw;
      while (rel > Math.PI) rel -= Math.PI * 2;
      while (rel < -Math.PI) rel += Math.PI * 2;
      this.spine.rotation.y = THREE.MathUtils.clamp(rel, -0.7, 0.7);
      const pitch = Math.atan2(dy, Math.hypot(dx, dz));
      const sway = this.windup > 0 ? 0 : Math.sin(state.time * 2.3) * 0.04;
      this.shoulders[1].rotation.set(-Math.PI / 2 - pitch + this.flinch + sway, 0, -0.12);
      this.elbows[1].rotation.x = 0;
      this.shoulders[0].rotation.set(-Math.PI / 2 - pitch + 0.25, 0, 0.55);
      this.elbows[0].rotation.x = -0.5;
      this.neck.rotation.set(-pitch * 0.7, 0, 0);
    }
    this.root.updateMatrixWorld(true);
  }

  shoot() {
    this.fireTimer = Math.max(0.7, 2.6 - this.level * 0.15) + Math.random() * 1.2;
    const muzzle = this.gun.localToWorld(this.muzzleLocal.clone());
    const player = state.player;
    const aim = player.torso.position.clone().add(new THREE.Vector3(0, Math.random() < 0.3 ? 0.15 : -0.15, 0));
    const dist = muzzle.distanceTo(aim);
    const spread = (0.45 + dist * 0.035) / (1 + this.level * 0.12);
    aim.x += (Math.random() - 0.5) * spread;
    aim.y += (Math.random() - 0.5) * spread * 0.7;
    aim.z += (Math.random() - 0.5) * spread;
    const vel = aim.sub(muzzle).normalize().multiplyScalar(26 + this.level);
    spawnBullet(muzzle, vel);
    play('npcShot', muzzle, 0.9);
    burst(muzzle, vel.clone().normalize(), 'spark', 5, 1);
  }
}

// --- Enemy bullets: visible, dodgeable projectiles. -----------------------------------
const bullets = [];
const bulletGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.35, 6).rotateX(Math.PI / 2);
const bulletMat = new THREE.MeshBasicMaterial({ color: 0xff9a3c });

function spawnBullet(pos, vel) {
  let b = bullets.find((x) => !x.active);
  if (!b) {
    b = { mesh: new THREE.Mesh(bulletGeo, bulletMat), pos: new THREE.Vector3(), vel: new THREE.Vector3(), active: false };
    state.scene.add(b.mesh);
    bullets.push(b);
  }
  b.active = true;
  b.life = 3;
  b.whoosh = false;
  b.pos.copy(pos);
  b.vel.copy(vel);
  b.mesh.visible = true;
}

export function clearBullets() {
  for (const b of bullets) { b.active = false; b.mesh.visible = false; }
}

export function updateBullets(dt) {
  const player = state.player;
  for (const b of bullets) {
    if (!b.active) continue;
    b.life -= dt;
    const a = b.pos.clone();
    const next = b.pos.clone().addScaledVector(b.vel, dt);
    let done = b.life <= 0;
    const dir = b.vel.clone().normalize();

    // Parry: bullets that hit your hands or a held item are blocked.
    if (!done) {
      for (const h of state.hands) {
        const held = h.held && h.held.kind === 'item' ? h.held.item : null;
        const handHit = h.tracked && segSphere(a, next, toThree(h.body.position, _v), 0.07);
        const itemHit = held && segSphere(a, next, toThree(held.body.position, _v2), 0.1);
        if (handHit || itemHit) {
          burst(handHit ? _v : _v2, dir.clone().negate(), 'block', 14, 2);
          play('tink', handHit ? _v : _v2, 0.9, 0.6);
          h.pulse(1, 60);
          state.game.onBlock();
          done = true;
          break;
        }
      }
    }
    if (!done) {
      const zone = player.hitTest(a, next);
      if (zone) {
        player.damage(zone === 'head' ? 34 : zone === 'body' ? 20 : 12);
        done = true;
      }
    }
    if (!done) {
      const hit = raycast(a, next, G.WORLD | G.PROP);
      if (hit) {
        burst(hit.point, hit.normal, hit.body.type === CANNON.Body.STATIC ? 'dust' : 'spark', 6, 2);
        play('impact', hit.point, 0.4, 1.4);
        if (hit.body.type === CANNON.Body.DYNAMIC) {
          const bb = hit.body;
          bb.applyImpulse(new CANNON.Vec3(dir.x * 3, dir.y * 3, dir.z * 3),
            new CANNON.Vec3(hit.point.x - bb.position.x, hit.point.y - bb.position.y, hit.point.z - bb.position.z));
        }
        done = true;
      }
    }
    if (!done && !b.whoosh && segSphere(a, next, player.headWorld, 1.0)) {
      b.whoosh = true;
      play('whoosh', next, 0.9, 1.6);
    }
    if (done) { b.active = false; b.mesh.visible = false; continue; }
    b.pos.copy(next);
    b.mesh.position.copy(b.pos);
    b.mesh.lookAt(_v.copy(b.pos).add(b.vel));
  }
}

export function npcsPreStep(h) { for (const n of state.npcs) n.preStep(h); }
export function updateNPCs(dt) { for (const n of [...state.npcs]) n.update(dt); updateBullets(dt); }
export function aliveCount() { return state.npcs.filter((n) => n.alive).length; }
export function clearNPCs() { for (const n of [...state.npcs]) n.remove(); clearBullets(); }
