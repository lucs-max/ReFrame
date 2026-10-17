// Shared game state, so modules can find each other without circular imports.
export const state = {
  scene: null,
  camera: null,
  rig: null,
  renderer: null,
  inVR: false,
  desktop: false,
  time: 0,
  grabbables: new Set(), // CANNON bodies that a hand can pick up
  weapons: [],
  npcs: [],
  buttons: [],
  player: null,
  hands: [],
  game: null,
};
