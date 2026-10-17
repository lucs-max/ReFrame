// Waves, scoring, hostile/training mode and the wrist / wall HUD.
import * as THREE from 'three';
import { state } from './state.js';
import { NPC, aliveCount, clearNPCs, clearBullets } from './npc.js';
import { raycast, G } from './physics.js';
import { play } from './audio.js';

export class Game {
  constructor() {
    this.hostile = true;
    this.wave = 0;
    this.kills = 0;
    this.headshots = 0;
    this.blocks = 0;
    this.queue = 0;
    this.spawnTimer = 0;
    this.waveActive = false;
    this.message = 'Press NEXT WAVE to start';
    this.messageTime = 9999;

    this.canvas = document.createElement('canvas');
    this.canvas.width = 512; this.canvas.height = 256;
    this.tex = new THREE.CanvasTexture(this.canvas);
    this.tex.colorSpace = THREE.SRGBColorSpace;
    this.hudDirty = true;
    this.hudTimer = 0;
  }

  // Called after the world and hands exist.
  initHUD() {
    const mat = new THREE.MeshBasicMaterial({ map: this.tex, transparent: true });
    const wrist = new THREE.Mesh(new THREE.PlaneGeometry(0.13, 0.065), mat);
    // On the back of the left wrist, readable when you check it like a watch.
    wrist.position.set(-0.04, 0, 0.09);
    wrist.rotation.y = -Math.PI / 2;
    const left = state.hands.find((h) => h.side === 'left');
    left.mesh.add(wrist);
    const board = new THREE.Mesh(new THREE.PlaneGeometry(2, 1), mat);
    board.position.set(-3.2, 2.1, 4.6);
    board.lookAt(0, 2.0, 8);
    state.scene.add(board);
    this.domHud = document.createElement('div');
    this.domHud.style.cssText = 'position:fixed;left:12px;bottom:12px;width:256px;height:128px;z-index:4;display:none;pointer-events:none';
    this.canvas.style.cssText = 'width:100%;height:100%';
    this.domHud.appendChild(this.canvas);
    document.body.appendChild(this.domHud);
  }

  say(msg, time = 3) { this.message = msg; this.messageTime = time; this.hudDirty = true; }

  startWave() {
    if (this.waveActive && aliveCount() > 0) { this.say('Finish this wave first'); return; }
    this.wave++;
    this.queue = Math.min(2 + this.wave, 10);
    this.spawnTimer = 0.5;
    this.waveActive = true;
    this.say(`Wave ${this.wave}: ${this.queue} enemies`);
    play('bell', null, 0.6);
  }

  toggleHostile() {
    this.hostile = !this.hostile;
    clearBullets();
    if (state.modeButton) state.modeButton.setLabel(this.hostile ? 'HOSTILE' : 'TRAINING');
    this.say(this.hostile ? 'Hostile: enemies shoot back' : 'Training: enemies hold fire');
  }

  spawnOne() {
    for (let tries = 0; tries < 20; tries++) {
      const x = (Math.random() * 2 - 1) * 20;
      const z = -23 + Math.random() * 10;
      const hit = raycast(new THREE.Vector3(x, 4, z), new THREE.Vector3(x, -0.1, z), G.WORLD | G.PROP);
      if (hit && hit.point.y > 0.05) continue;
      const n = new NPC(x, z, this.wave);
      if (Math.random() < 0.5) n.state = 'combat';
      return;
    }
  }

  noise(pos) {
    for (const n of state.npcs) {
      if (n.alive && n.root.position.distanceTo(pos) < 32 && n.state === 'patrol') {
        n.state = 'combat';
        n.lastKnown.copy(pos);
        n.lastSeen = state.time;
      }
    }
  }

  onKill(npc, headshot) {
    this.kills++;
    if (headshot) { this.headshots++; this.say('Headshot!', 1.5); }
    this.hudDirty = true;
  }
  onBlock() { this.blocks++; this.say('Blocked!', 1); }

  onPlayerDeath() {
    this.say(`You died on wave ${this.wave}`, 4);
    clearBullets();
  }
  onPlayerRespawn() {
    clearNPCs();
    this.waveActive = false;
    this.wave = Math.max(0, this.wave - 1);
    this.queue = 0;
    this.say('Press NEXT WAVE to retry', 9999);
  }

  update(dt) {
    if (this.queue > 0 && aliveCount() < 6) {
      this.spawnTimer -= dt;
      if (this.spawnTimer <= 0) { this.spawnOne(); this.queue--; this.spawnTimer = 1.4; this.hudDirty = true; }
    }
    if (this.waveActive && this.queue === 0 && aliveCount() === 0) {
      this.waveActive = false;
      this.say(`Wave ${this.wave} cleared! Press NEXT WAVE`, 9999);
      play('bell', null, 0.8, 1.25);
    }
    this.messageTime -= dt;
    this.hudTimer -= dt;
    if (this.hudTimer <= 0) { this.hudTimer = 0.1; this.drawHUD(); }
  }

  drawHUD() {
    const g = this.canvas.getContext('2d');
    const p = state.player;
    g.clearRect(0, 0, 512, 256);
    g.fillStyle = 'rgba(10,14,18,0.82)';
    g.fillRect(0, 0, 512, 256);
    // Health bar
    g.fillStyle = '#333';
    g.fillRect(20, 20, 472, 26);
    g.fillStyle = p.hp > 50 ? '#3fb950' : p.hp > 25 ? '#d29922' : '#f85149';
    g.fillRect(20, 20, 472 * (p.hp / 100), 26);
    g.fillStyle = '#fff';
    g.font = 'bold 22px sans-serif';
    g.fillText(`HP ${Math.ceil(p.hp)}`, 28, 41);
    // Ammo per hand
    g.font = 'bold 28px sans-serif';
    let y = 86;
    for (const h of state.hands) {
      const item = h.held && h.held.kind === 'item' ? h.held.item : null;
      let txt = `${h.side === 'left' ? 'L' : 'R'}: ${h.held ? (h.held.kind === 'support' ? 'support grip' : item ? (item.isWeapon ? item.def.name : 'ammo') : 'object') : 'empty'}`;
      if (item && item.isWeapon) {
        txt += `  ${item.ammo}/${item.def.cap}`;
        if (item.def.feed === 'mag' && !item.hasMag) txt += '  NO MAG';
      }
      g.fillStyle = item && item.isWeapon && item.ammo === 0 ? '#f85149' : '#e6edf3';
      g.fillText(txt, 20, y);
      y += 36;
    }
    g.fillStyle = '#f0883e';
    g.font = 'bold 24px sans-serif';
    g.fillText(`Wave ${this.wave}  Enemies ${aliveCount() + this.queue}  Kills ${this.kills}  HS ${this.headshots}`, 20, 172);
    g.fillStyle = '#8b949e';
    g.font = '20px sans-serif';
    g.fillText(`${this.hostile ? 'Hostile' : 'Training'} · Walk: ${p.locomotion === 'swing' ? 'arm swing' : 'stick'}${p.chestTracked ? ' · body tracked' : ''}`, 20, 204);
    if (this.messageTime > 0) {
      g.fillStyle = '#fff';
      g.font = 'bold 24px sans-serif';
      g.fillText(this.message, 20, 238);
    }
    this.tex.needsUpdate = true;
  }
}
