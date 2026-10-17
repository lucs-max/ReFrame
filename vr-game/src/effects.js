// Visual effects: muzzle flashes, tracers, particles and bullet holes. All pooled.
import * as THREE from 'three';

let scene;
const tracers = [];
const decals = [];
let decalIndex = 0;
let flashLight, flashMesh, flashTime = 0;

const MAX_P = 600;
let points, pPos, pCol, pVel, pLife, pNext = 0;

export function initEffects(s) {
  scene = s;

  const tracerGeo = new THREE.BoxGeometry(1, 1, 1);
  tracerGeo.translate(0, 0, -0.5);
  for (let i = 0; i < 40; i++) {
    const m = new THREE.Mesh(tracerGeo, new THREE.MeshBasicMaterial({
      color: 0xffd27a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
    m.visible = false;
    m.userData.life = 0;
    scene.add(m);
    tracers.push(m);
  }

  const decalGeo = new THREE.CircleGeometry(0.018, 10);
  const decalMat = new THREE.MeshBasicMaterial({ color: 0x111111, polygonOffset: true, polygonOffsetFactor: -4, depthWrite: false });
  for (let i = 0; i < 100; i++) {
    const d = new THREE.Mesh(decalGeo, decalMat);
    d.visible = false;
    scene.add(d);
    decals.push(d);
  }

  flashLight = new THREE.PointLight(0xffb060, 0, 8, 2);
  scene.add(flashLight);
  const flashGeo = new THREE.OctahedronGeometry(0.06, 0);
  flashGeo.scale(1, 1, 2.2);
  flashMesh = new THREE.Mesh(flashGeo, new THREE.MeshBasicMaterial({ color: 0xffe09a, transparent: true,
    blending: THREE.AdditiveBlending, depthWrite: false }));
  flashMesh.visible = false;
  scene.add(flashMesh);

  const geo = new THREE.BufferGeometry();
  pPos = new Float32Array(MAX_P * 3).fill(-999);
  pCol = new Float32Array(MAX_P * 3);
  pVel = new Float32Array(MAX_P * 3);
  pLife = new Float32Array(MAX_P);
  geo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(pCol, 3));
  points = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.025, vertexColors: true, sizeAttenuation: true }));
  points.frustumCulled = false;
  scene.add(points);
}

export function tracer(from, to, color = 0xffd27a, width = 0.008, life = 0.07) {
  const t = tracers.find((m) => m.userData.life <= 0) || tracers[0];
  const len = from.distanceTo(to);
  t.position.copy(from);
  t.lookAt(to);
  t.scale.set(width, width, len);
  t.material.color.setHex(color);
  t.material.opacity = 0.9;
  t.userData.life = t.userData.maxLife = life;
  t.visible = true;
}

export function muzzleFlash(pos, quat) {
  flashLight.position.copy(pos);
  flashLight.intensity = 6;
  flashMesh.position.copy(pos);
  flashMesh.quaternion.copy(quat);
  flashMesh.rotateZ(Math.random() * Math.PI);
  flashMesh.scale.setScalar(0.7 + Math.random() * 0.6);
  flashMesh.visible = true;
  flashTime = 0.05;
}

const COLORS = {
  spark: [1, 0.8, 0.35],
  dust: [0.55, 0.52, 0.48],
  hit: [0.55, 0.05, 0.05],
  block: [0.5, 0.8, 1],
};
export function burst(pos, normal, kind = 'spark', count = 10, speed = 2.5) {
  const c = COLORS[kind] || COLORS.spark;
  for (let n = 0; n < count; n++) {
    const i = pNext; pNext = (pNext + 1) % MAX_P;
    pPos[i * 3] = pos.x; pPos[i * 3 + 1] = pos.y; pPos[i * 3 + 2] = pos.z;
    const s = speed * (0.3 + Math.random());
    pVel[i * 3] = (normal.x + (Math.random() - 0.5) * 1.4) * s;
    pVel[i * 3 + 1] = (normal.y + (Math.random() - 0.5) * 1.4) * s;
    pVel[i * 3 + 2] = (normal.z + (Math.random() - 0.5) * 1.4) * s;
    pCol[i * 3] = c[0]; pCol[i * 3 + 1] = c[1]; pCol[i * 3 + 2] = c[2];
    pLife[i] = 0.3 + Math.random() * 0.4;
  }
}

const _n = new THREE.Vector3();
export function bulletHole(point, normal, parent = null) {
  const d = decals[decalIndex];
  decalIndex = (decalIndex + 1) % decals.length;
  d.removeFromParent();
  d.position.copy(point).addScaledVector(normal, 0.003);
  d.lookAt(_n.copy(d.position).add(normal));
  if (parent) parent.attach(d); else scene.add(d);
  d.visible = true;
}

export function updateEffects(dt) {
  for (const t of tracers) {
    if (t.userData.life <= 0) continue;
    t.userData.life -= dt;
    t.material.opacity = Math.max(0, t.userData.life / t.userData.maxLife) * 0.9;
    if (t.userData.life <= 0) t.visible = false;
  }
  if (flashTime > 0) {
    flashTime -= dt;
    if (flashTime <= 0) { flashLight.intensity = 0; flashMesh.visible = false; }
  }
  for (let i = 0; i < MAX_P; i++) {
    if (pLife[i] <= 0) continue;
    pLife[i] -= dt;
    pVel[i * 3 + 1] -= 9.8 * dt;
    pPos[i * 3] += pVel[i * 3] * dt;
    pPos[i * 3 + 1] += pVel[i * 3 + 1] * dt;
    pPos[i * 3 + 2] += pVel[i * 3 + 2] * dt;
    if (pPos[i * 3 + 1] < 0.005) { pPos[i * 3 + 1] = 0.005; pVel[i * 3] *= 0.5; pVel[i * 3 + 1] *= -0.3; pVel[i * 3 + 2] *= 0.5; }
    if (pLife[i] <= 0) pPos[i * 3 + 1] = -999;
  }
  points.geometry.attributes.position.needsUpdate = true;
  points.geometry.attributes.color.needsUpdate = true;
}
