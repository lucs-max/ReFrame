# Rigid Front VR

A physics-driven VR shooter that runs in the browser with WebXR. It works on Meta Quest's
built-in browser, on PC VR (SteamVR or Quest Link with Chrome or Edge), and with mouse and
keyboard on a normal desktop.

No build step and no install. three.js and the cannon-es physics engine are included in `lib/`,
so the game also runs offline.

## Features

- **Rigid-body player.** Your body is a physics capsule that follows your real head. You can
  walk around your room, use the stick (with acceleration and momentum), sprint, jump and
  climb stairs and ramps. Walls stop you, you can lean over low cover, and your view fades
  to black if you push your head into a wall.
- **Realistic walking.** Procedural legs plant their feet, take steps with two-bone IK and
  play footstep sounds, whether you walk with the stick or for real. There is also an
  **arm-swing** mode: swing your arms like a runner to walk.
- **Physics hands.** Each hand is a rigid body that chases the controller. Hands collide
  with the world, push crates, punch enemies, and grab, carry and throw anything loose,
  including ragdolls. Heavy objects sag because the grab is a force-limited joint.
  Articulated **hand tracking** works too (make a fist to grab, curl your index finger to fire).
- **Chest tracking and holsters.** Your chest is tracked with WebXR body tracking when the
  headset provides it (Quest). Otherwise it is estimated from your head and hands. A pistol
  and an SMG hang on your hips, a shotgun is on your back, and ammo pouches sit on your belt.
  Your torso is a hit box, so you can dodge with your body.
- **Weapons.** Pistol (semi-auto), SMG (full-auto, optional two-hand grip) and shotgun
  (9 pellets, two-handed), plus spares on the table. They have physical recoil, muzzle flash,
  tracers, bouncing shell casings, bullet holes, haptics and impulses that knock objects
  around. **Reload by hand:** eject the magazine, grab a new one from your belt and push it into
  the magwell. The shotgun loads one shell at a time.
- **Enemies.** Soldiers patrol, spot you, strafe, take cover and shoot back with visible
  bullets you can dodge or **block with your gun or hands**. Each body part takes different
  damage (headshots do 3.5x). When killed they become ragdolls with cone-twist joints that
  you can shoot, push, drag and throw. Some drop their pistol.
- **Waves and modes.** Press the red NEXT WAVE button to start a wave. The blue button switches
  between Hostile and Training (enemies hold fire). A wrist display and a wall scoreboard
  show health, ammo, wave and kills.

## Run it

Serve the folder from any static web server:

```bash
cd vr-game
python3 -m http.server 8000
```

- **Desktop:** open http://localhost:8000 and click **Play on desktop**.
- **PC VR** (SteamVR or Quest Link): open http://localhost:8000 in Chrome or Edge on the PC and
  click **Enter VR**.
- **Quest standalone:** WebXR only runs on HTTPS or `localhost`. You can either:
  - connect the Quest over USB and run `adb reverse tcp:8000 tcp:8000`, then open
    `http://localhost:8000` in the Quest browser, or
  - host the `vr-game` folder anywhere with HTTPS (GitHub Pages, Netlify, …) and open that URL.

## Controls

| VR | Action |
|---|---|
| Left stick | Walk (click to sprint) |
| Right stick | Snap turn left and right, push up to jump |
| Grip | Grab and hold. Release near a holster to holster a weapon |
| Trigger | Fire |
| A / X | Eject the magazine of the gun in that hand |
| B | Start the next wave |
| Y | Switch walking mode: stick or arm-swing |
| Off-hand grip on the foregrip | Two-handed aim (SMG, shotgun) |
| Off-hand grip at the belt front | Take a magazine or shell for the gun you're holding |

| Desktop | Action |
|---|---|
| WASD, mouse | Walk, look (Shift sprints, Space jumps, C crouches) |
| Left click | Fire |
| E / Q | Grab what you look at / throw what you hold |
| R | Reload |
| 1 2 3 | Pistol, SMG, shotgun |
| Enter / T / V | Next wave / hostile or training / walking mode |

## Code map

| File | What it does |
|---|---|
| `src/main.js` | Renderer, WebXR session, input mapping, desktop controls, main loop |
| `src/physics.js` | cannon-es world, collision groups, pose-driving helpers, raycasts |
| `src/player.js` | Body capsule, locomotion, head collision, chest estimation, holsters, legs IK, health |
| `src/hands.js` | Physics hands, controller and hand-tracking input, grab, throw, holster |
| `src/weapons.js` | Weapon models and stats, firing, recoil, casings, magazines and shells |
| `src/npc.js` | Enemy skeleton animation, AI, shooting, bullets, ragdolls |
| `src/world.js` | Level geometry, props and push buttons |
| `src/game.js` | Waves, scoring, modes, wrist and wall HUD |
| `src/effects.js` | Tracers, muzzle flash, particles, bullet holes |
| `src/audio.js` | Procedurally generated 3D sound effects |

Physics runs at a fixed 90 Hz. Each step: locomotion moves the tracking origin and the body
capsule follows the head. The hands are driven toward the controllers by velocity, so they
stop at walls. Held guns are kinematic and follow the physics hand, which keeps aiming
steady. Live enemies are kinematic bodies posed by a procedural skeleton, and on death they
switch to dynamic bodies joined by ragdoll constraints.

Licenses for the bundled libraries are in `lib/`.
