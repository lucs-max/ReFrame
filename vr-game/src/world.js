// The level: an outdoor compound with cover, stairs, a ramp, a weapon table and loose props.
import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { world, G, materials, link } from './physics.js';
import { state } from './state.js';
import { play } from './audio.js';

export const ARENA = 26; // half size of the walled area

function gridTexture(base, line, size = 512, cells = 8) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  g.fillStyle = base;
  g.fillRect(0, 0, size, size);
  for (let i = 0; i < 400; i++) {
    g.fillStyle = `rgba(0,0,0,${Math.random() * 0.06})`;
    g.fillRect(Math.random() * size, Math.random() * size, 6 + Math.random() * 20, 6 + Math.random() * 20);
  }
  g.strokeStyle = line;
  g.lineWidth = 3;
  const s = size / cells;
  for (let i = 0; i <= cells; i++) {
    g.beginPath(); g.moveTo(i * s, 0); g.lineTo(i * s, size); g.stroke();
    g.beginPath(); g.moveTo(0, i * s); g.lineTo(size, i * s); g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

const matCache = {};
function mat(color) {
  if (!matCache[color]) matCache[color] = new THREE.MeshStandardMaterial({ color, roughness: 0.85 });
  return matCache[color];
}

export function staticBox(w, h, d, x, y, z, color = 0x8a8f98, rotY = 0, rotX = 0, visible = true) {
  const body = new CANNON.Body({ mass: 0, material: materials.ground, collisionFilterGroup: G.WORLD });
  body.addShape(new CANNON.Box(new CANNON.Vec3(w / 2, h / 2, d / 2)));
  body.position.set(x, y, z);
  body.quaternion.setFromEuler(rotX, rotY, 0, 'YXZ');
  world.addBody(body);
  if (visible) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
    m.position.copy(body.position);
    m.quaternion.copy(body.quaternion);
    m.castShadow = m.receiveShadow = true;
    state.scene.add(m);
  }
  return body;
}

export function dynamicBox(w, h, d, x, y, z, mass, color) {
  const body = new CANNON.Body({ mass, material: materials.prop, collisionFilterGroup: G.PROP,
    collisionFilterMask: G.WORLD | G.PROP | G.HAND | G.PLAYER | G.NPC | G.HELD });
  body.addShape(new CANNON.Box(new CANNON.Vec3(w / 2, h / 2, d / 2)));
  body.position.set(x, y, z);
  body.linearDamping = 0.05;
  body.angularDamping = 0.1;
  body.sleepSpeedLimit = 0.15;
  world.addBody(body);
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
  m.castShadow = m.receiveShadow = true;
  state.scene.add(m);
  link(body, m);
  body.userData.grabbable = true;
  body.userData.kind = 'prop';
  state.grabbables.add(body);
  addImpactSound(body);
  return body;
}

function barrel(x, z) {
  const body = new CANNON.Body({ mass: 12, material: materials.prop, collisionFilterGroup: G.PROP,
    collisionFilterMask: G.WORLD | G.PROP | G.HAND | G.PLAYER | G.NPC | G.HELD });
  body.addShape(new CANNON.Cylinder(0.28, 0.28, 0.9, 12));
  body.position.set(x, 0.46, z);
  body.angularDamping = 0.2;
  world.addBody(body);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.9, 16), mat(0x2f6d4f));
  m.castShadow = m.receiveShadow = true;
  state.scene.add(m);
  link(body, m);
  body.userData.grabbable = true;
  body.userData.kind = 'prop';
  state.grabbables.add(body);
  addImpactSound(body);
}

function addImpactSound(body) {
  let last = 0;
  body.addEventListener('collide', (e) => {
    const v = Math.abs(e.contact.getImpactVelocityAlongNormal());
    if (v < 1.5 || state.time - last < 0.08) return;
    last = state.time;
    play('impact', body.position, Math.min(1, v / 8), 0.7 + Math.min(v, 6) * 0.05);
  });
}

// A physical push button: press it with a hand (or the desktop "use" key) to trigger it.
function button(x, y, z, label, color, onPress) {
  const base = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.06, 0.28), mat(0x30343a));
  base.position.set(x, y, z);
  state.scene.add(base);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.05, 20),
    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.3 }));
  cap.position.set(x, y + 0.05, z);
  state.scene.add(cap);

  const c = document.createElement('canvas');
  c.width = 256; c.height = 64;
  const tex = new THREE.CanvasTexture(c);
  const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 0.1), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
  sign.position.set(x, y + 0.2, z);
  sign.lookAt(x, y + 0.2, 8); // face the spawn point
  state.scene.add(sign);
  const setLabel = (text) => {
    const g = c.getContext('2d');
    g.clearRect(0, 0, 256, 64);
    g.fillStyle = 'rgba(0,0,0,0.6)';
    g.fillRect(0, 0, 256, 64);
    g.fillStyle = '#fff';
    g.font = 'bold 30px sans-serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(text, 128, 34);
    tex.needsUpdate = true;
  };
  setLabel(label);
  const b = { cap, pos: new THREE.Vector3(x, y + 0.05, z), pressed: false, cooldown: 0, onPress, setLabel };
  state.buttons.push(b);
  return b;
}

export function updateButtons(dt, pressPoints) {
  for (const b of state.buttons) {
    b.cooldown -= dt;
    let down = false;
    for (const p of pressPoints) {
      const dx = p.x - b.pos.x, dz = p.z - b.pos.z, dy = p.y - b.pos.y;
      if (dx * dx + dz * dz < 0.09 * 0.09 && dy < 0.06 && dy > -0.04) down = true;
    }
    b.cap.position.y = b.pos.y - (down ? 0.025 : 0);
    if (down && !b.pressed && b.cooldown <= 0) {
      b.cooldown = 0.6;
      play('click', b.pos, 0.8);
      b.onPress();
    }
    b.pressed = down;
  }
}

export function buildWorld() {
  const scene = state.scene;
  scene.background = new THREE.Color(0x9fb8cf);
  scene.fog = new THREE.Fog(0x9fb8cf, 30, 90);

  const hemi = new THREE.HemisphereLight(0xdfefff, 0x4a4436, 1.1);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
  sun.position.set(12, 22, 8);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  const sc = sun.shadow.camera;
  sc.left = -30; sc.right = 30; sc.top = 30; sc.bottom = -30; sc.near = 1; sc.far = 60;
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  // Ground
  const groundTex = gridTexture('#6b6f5e', 'rgba(255,255,255,0.12)');
  groundTex.repeat.set(40, 40);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(160, 160),
    new THREE.MeshStandardMaterial({ map: groundTex, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const gBody = new CANNON.Body({ mass: 0, material: materials.ground, collisionFilterGroup: G.WORLD });
  gBody.addShape(new CANNON.Plane());
  gBody.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
  world.addBody(gBody);

  // Perimeter walls
  const W = ARENA * 2;
  staticBox(W, 3, 0.4, 0, 1.5, -ARENA, 0x7d7468);
  staticBox(W, 3, 0.4, 0, 1.5, ARENA, 0x7d7468);
  staticBox(0.4, 3, W, -ARENA, 1.5, 0, 0x7d7468);
  staticBox(0.4, 3, W, ARENA, 1.5, 0, 0x7d7468);

  // Spawn bunker: a low wall the player can lean over and shoot from.
  staticBox(6, 1.1, 0.3, 0, 0.55, 4.5, 0x6f7680);
  staticBox(0.3, 1.1, 3, -3, 0.55, 6, 0x6f7680);
  staticBox(0.3, 1.1, 3, 3, 0.55, 6, 0x6f7680);

  // Weapon table
  staticBox(1.8, 0.06, 0.7, 1.4, 0.9, 7.2, 0x5b4636);
  for (const [dx, dz] of [[-0.8, -0.3], [0.8, -0.3], [-0.8, 0.3], [0.8, 0.3]]) staticBox(0.06, 0.87, 0.06, 1.4 + dx, 0.435, 7.2 + dz, 0x3e3026);

  // Cover blocks across the field
  const covers = [
    [-6, -2, 2.4, 1.2, 0.8], [5, -4, 1.4, 1.4, 1.4], [-2, -9, 3, 1.0, 0.6], [8, -11, 1, 2.2, 3],
    [-10, -12, 2, 1.5, 2], [2, -16, 4, 1.2, 0.8], [-7, -19, 1.2, 2.5, 1.2], [11, -19, 2.5, 1.2, 1],
    [-14, -4, 1, 2, 4], [15, 0, 1.2, 1.2, 1.2], [0, -22, 6, 2, 0.6], [-17, -16, 2, 1, 2],
  ];
  for (const [x, z, w, h, d] of covers) staticBox(w, h, d, x, h / 2, z, 0x8a8f98);

  // Raised platform with stairs (visual steps + smooth collision ramp) and a ramp on the far side.
  staticBox(6, 1.5, 4, -16, 0.75, 8, 0x767c86);
  const steps = 8;
  for (let i = 0; i < steps; i++) {
    const h = (i + 1) * (1.5 / steps);
    staticBox(1.4, h, 0.35, -12.3, h / 2, 9.4 - i * 0.35 + 0, 0x8d939c, 0, 0, true);
  }
  // Hidden collision slope over the stairs so walking up them feels smooth.
  const stairLen = steps * 0.35;
  const slope = Math.atan2(1.5, stairLen);
  staticBox(1.4, 0.05, Math.hypot(stairLen, 1.5), -12.3, 0.75, 9.4 - stairLen / 2 + 0.175, 0, 0, slope, false);
  staticBox(1.5, 0.1, 5, -16, 0.75, 3.6, 0x8d939c, 0, -Math.atan2(1.5, 4.8));

  // Dynamic props: crate stacks, barrels, planks.
  const crate = (x, y, z, s = 0.6) => dynamicBox(s, s, s, x, y, z, 8 * s, 0xa07a4a);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3 - i; j++) crate(-4 + j * 0.62 + i * 0.31, 0.3 + i * 0.6, -5);
  for (let i = 0; i < 4; i++) crate(6.5, 0.3 + i * 0.6, -7, 0.6);
  crate(3, 0.25, 1, 0.5); crate(3.6, 0.25, 1.2, 0.5); crate(-2.5, 0.2, 2, 0.4);
  for (const [x, z] of [[-8, -6], [-8.6, -6.3], [9, -3], [12, -14], [-3, -14]]) barrel(x, z);
  dynamicBox(0.15, 0.05, 2.2, 0.6, 1.0, 7.0, 3, 0x9c7b52).userData.kind = 'plank';
  // Little things on the table to toss around
  dynamicBox(0.12, 0.12, 0.12, 2.0, 1.0, 7.0, 0.4, 0xd04a3a);
  dynamicBox(0.1, 0.18, 0.1, 2.15, 1.0, 7.3, 0.4, 0x3a7fd0);

  // Buttons at the spawn wall.
  const game = state.game;
  button(-1.2, 1.1, 4.62, 'NEXT WAVE', 0xd03a2a, () => game.startWave());
  state.modeButton = button(-0.6, 1.1, 4.62, game.hostile ? 'HOSTILE' : 'TRAINING', 0x2a8ad0, () => game.toggleHostile());

  return { ground };
}
