// Physics world setup and small helpers shared by every module.
import * as CANNON from 'cannon-es';
import * as THREE from 'three';

export const STEP = 1 / 90;

// Collision groups.
export const G = {
  WORLD: 1,   // static level geometry
  PROP: 2,    // loose dynamic objects: crates, weapons, magazines
  HAND: 4,    // the player's physics hands
  PLAYER: 8,  // the player's body capsule
  NPC: 16,    // enemy body parts
  CASING: 32, // spent shell casings (only hit the world)
  HELD: 64,   // objects currently held in a hand
};

export const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -9.82, 0) });
world.broadphase = new CANNON.SAPBroadphase(world);
world.allowSleep = true;
world.solver.iterations = 12;

export const materials = {
  ground: new CANNON.Material('ground'),
  player: new CANNON.Material('player'),
  prop: new CANNON.Material('prop'),
  hand: new CANNON.Material('hand'),
};
world.addContactMaterial(new CANNON.ContactMaterial(materials.player, materials.ground, { friction: 0, restitution: 0 }));
world.addContactMaterial(new CANNON.ContactMaterial(materials.player, materials.prop, { friction: 0, restitution: 0 }));
world.addContactMaterial(new CANNON.ContactMaterial(materials.prop, materials.ground, { friction: 0.5, restitution: 0.15 }));
world.addContactMaterial(new CANNON.ContactMaterial(materials.prop, materials.prop, { friction: 0.45, restitution: 0.1 }));
world.addContactMaterial(new CANNON.ContactMaterial(materials.hand, materials.prop, { friction: 0.9, restitution: 0 }));
world.addContactMaterial(new CANNON.ContactMaterial(materials.hand, materials.ground, { friction: 0.6, restitution: 0 }));

// Every body that has a mesh mirroring it. Synced once per rendered frame.
const synced = [];
export function link(body, mesh) {
  synced.push({ body, mesh });
  body.userData = body.userData || {};
  body.userData.mesh = mesh;
}
export function unlink(body) {
  const i = synced.findIndex((s) => s.body === body);
  if (i >= 0) synced.splice(i, 1);
}
export function syncMeshes() {
  for (const { body, mesh } of synced) {
    mesh.position.copy(body.position);
    mesh.quaternion.copy(body.quaternion);
  }
}

// Conversions.
export const v3 = (v) => new CANNON.Vec3(v.x, v.y, v.z);
export const toThree = (v, out = new THREE.Vector3()) => out.set(v.x, v.y, v.z);

const _q = new CANNON.Quaternion();
// Drive a kinematic (or dynamic) body to reach a pose within one physics step,
// using velocities so contacts still see a moving body.
export function driveToPose(body, pos, quat, h = STEP, maxSpeed = 30) {
  body.velocity.set((pos.x - body.position.x) / h, (pos.y - body.position.y) / h, (pos.z - body.position.z) / h);
  const s = body.velocity.length();
  if (s > maxSpeed) body.velocity.scale(maxSpeed / s, body.velocity);
  // q = target * conj(current)
  const c = body.quaternion;
  _q.set(-c.x, -c.y, -c.z, c.w);
  const tx = quat.x, ty = quat.y, tz = quat.z, tw = quat.w;
  let qx = tw * _q.x + tx * _q.w + ty * _q.z - tz * _q.y;
  let qy = tw * _q.y - tx * _q.z + ty * _q.w + tz * _q.x;
  let qz = tw * _q.z + tx * _q.y - ty * _q.x + tz * _q.w;
  let qw = tw * _q.w - tx * _q.x - ty * _q.y - tz * _q.z;
  if (qw < 0) { qx = -qx; qy = -qy; qz = -qz; qw = -qw; }
  const sinHalf = Math.sqrt(qx * qx + qy * qy + qz * qz);
  if (sinHalf < 1e-6) { body.angularVelocity.set(0, 0, 0); return; }
  const angle = 2 * Math.atan2(sinHalf, qw);
  const k = angle / sinHalf / h;
  body.angularVelocity.set(qx * k, qy * k, qz * k);
  body.wakeUp();
}

export function setPose(body, pos, quat) {
  body.position.set(pos.x, pos.y, pos.z);
  body.quaternion.set(quat.x, quat.y, quat.z, quat.w);
  body.previousPosition.copy(body.position);
  body.interpolatedPosition.copy(body.position);
  body.velocity.set(0, 0, 0);
  body.angularVelocity.set(0, 0, 0);
  body.aabbNeedsUpdate = true;
}

// Distance from a point to a body's world AABB (0 when inside).
export function distToBody(body, p) {
  if (body.aabbNeedsUpdate) body.updateAABB();
  const { lowerBound: lo, upperBound: hi } = body.aabb;
  const dx = Math.max(lo.x - p.x, 0, p.x - hi.x);
  const dy = Math.max(lo.y - p.y, 0, p.y - hi.y);
  const dz = Math.max(lo.z - p.z, 0, p.z - hi.z);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

const _ray = new CANNON.RaycastResult();
const _from = new CANNON.Vec3();
const _to = new CANNON.Vec3();
// Closest hit between two THREE/CANNON points. Returns null or a fresh result object.
export function raycast(from, to, mask) {
  _from.set(from.x, from.y, from.z);
  _to.set(to.x, to.y, to.z);
  _ray.reset();
  world.raycastClosest(_from, _to, { collisionFilterMask: mask, skipBackfaces: true }, _ray);
  if (!_ray.hasHit) return null;
  return {
    body: _ray.body,
    shape: _ray.shape,
    point: toThree(_ray.hitPointWorld),
    normal: toThree(_ray.hitNormalWorld),
    distance: _ray.distance,
  };
}
