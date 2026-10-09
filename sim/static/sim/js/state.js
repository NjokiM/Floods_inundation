// Tiny observable store for the sim. Plain ES module, no framework.
const listeners = new Map();

export const state = {
  site: "nairobi",           // 'nairobi' | 'tana'
  stage: 0.0,                // metres
  stageCm: 0,                // cache of stage*100 (int)
  scenario: null,            // set after load (id string)
  scenarioBlockage: 1.0,     // informal-drain factor of the active scenario
  playing: false,
  playT: 0,                  // scenario time 0..1
  layers: { city: true, hand: false, response: false },
  view: "lab",               // lab | exploded | studio
  exploded: 0,               // animated 0..1 offset factor
  ready: false,
};

const DATA = { nairobi: null, tana: null };   // cached site data

export function on(key, fn) {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key).add(fn);
  return () => listeners.get(key).delete(fn);
}

export function set(patch) {
  for (const k in patch) {
    if (state[k] === patch[k]) continue;
    state[k] = patch[k];
    const set_ = listeners.get(k);
    if (set_) for (const fn of set_) fn(state[k], state);
  }
}

export function siteData(site = state.site) { return DATA[site]; }

export function cacheSiteData(site, data) { DATA[site] = data; }
