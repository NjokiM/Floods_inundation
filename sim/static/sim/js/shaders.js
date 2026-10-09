// All scene materials. Original GLSL, lean by design.
// Conventions:
//   - scene units are meters; the world group carries scale.y = vertical Exaggeration
//   - grid attributes (terrain/water): aElev, aThresh, aOut (Float32 meters),
//     aSettle (0/1/2), aSlope (int8 normal xz ticks, |grad|*100), aCellUv (u,v)
//   - submerged iff aThresh < uStage; depth = aOut + uStage − aElev
//   - buildings: instance attrs iPos(x,z,rot), iDim(w,l,hM,class), iHand(th,out,elev)
//   - a "wet" state and a fog are computed per fragment
import * as THREE from "three";

const FOG = /* glsl */`
vec3 applyFog(vec3 col, float dist, vec3 fogColor, float density) {
  float f = 1.0 - exp(-density * density * dist * dist);
  return mix(col, fogColor, clamp(f, 0.0, 1.0));
}`;

const VS_GRID_BASE = /* glsl */`
attribute float aElev;
attribute float aThresh;
attribute float aOut;
attribute float aSettle;
attribute vec2 aSlope;
attribute vec2 aCellUv;
uniform float uStage;
uniform float uBlock;
varying vec3 vWorld;
varying vec2 vUv;
varying float vDepth;
varying float vHand;
varying float vWet;
void main() {
  float block = mix(uBlock, 1.0, step(0.5, aSettle));
  float thresh = aThresh * block;
  vWet = step(thresh, uStage);
  vHand = aThresh;
  // depth must use the SAME effective threshold as the wet test above, or cells
  // that flood only because of drain blockage get a negative depth and get
  // discarded — making every blockage scenario look identical to the baseline.
  // (aOut == aElev - aThresh, so this is unchanged when uBlock == 1.)
  vDepth = (uStage - thresh) * vWet;
  vec3 p = position;
  p.y = aElev;
  vUv = aCellUv;
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const FS_TERRAIN = /* glsl */`
uniform sampler2D uMap;
uniform int uHasMap;
uniform float uHeatA;
uniform vec3 uFogCol;
uniform float uFogD;
varying vec3 vWorld;
varying vec3 vNormalW;
varying vec2 vUv;
varying float vDepth;
varying float vHand;
varying float vWet;
${FOG}
vec3 handRamp(float h) {
  float t = clamp(h / 9.0, 0.0, 1.0);
  vec3 a = mix(vec3(0.78, 0.13, 0.10), vec3(0.93, 0.60, 0.14), smoothstep(0.0, 0.30, t));
  vec3 b = mix(a, vec3(0.55, 0.78, 0.70), smoothstep(0.22, 0.52, t));
  return mix(b, vec3(0.88, 0.91, 0.86), smoothstep(0.5, 0.92, t));
}
void main() {
  vec3 alb;
  if (uHasMap == 1) {
    alb = texture2D(uMap, vUv).rgb;
  } else {
    alb = mix(vec3(0.30, 0.33, 0.27), vec3(0.54, 0.50, 0.39), clamp(vHand * 0.055, 0.0, 1.0));
  }
  float sun = max(dot(normalize(vNormalW), normalize(vec3(-0.55, 0.62, 0.45))), 0.0);
  vec3 col = alb * (0.40 + 0.72 * sun);
  // HAND heat overlay (Risk layer)
  col = mix(col, handRamp(vHand) * (0.55 + 0.5 * sun), uHeatA);
  // standing water tint under the water mesh
  if (vDepth > 0.0) {
    float d = min(vDepth, 3.0);
    vec3 deep = mix(vec3(0.10, 0.30, 0.36), vec3(0.045, 0.16, 0.28), smoothstep(0.3, 2.6, d));
    col = mix(col, deep, clamp(0.30 + d * 0.30, 0.0, 0.9));
  }
  gl_FragColor = vec4(applyFog(col, length(vWorld - cameraPosition), uFogCol, uFogD), 1.0);
}`;

export function makeTerrainMaterial(map) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uMap: { value: map || null },
      uHasMap: { value: map ? 1 : 0 },
      uHeatA: { value: 0 },
      uStage: { value: 0 },
      uBlock: { value: 1 },
      uFogCol: { value: new THREE.Color("#1d211e") },
      uFogD: { value: 0.000045 },
    },
    vertexShader: /* glsl */`
attribute float aElev;
attribute float aThresh;
attribute float aOut;
attribute float aSettle;
attribute vec2 aSlope;
attribute vec2 aCellUv;
uniform float uStage;
uniform float uBlock;
varying vec3 vWorld;
varying vec3 vNormalW;
varying vec2 vUv;
varying float vDepth;
varying float vHand;
varying float vWet;
void main() {
  float block = mix(uBlock, 1.0, step(0.5, aSettle));
  float thresh = aThresh * block;
  vWet = step(thresh, uStage);
  vHand = aThresh;
  vDepth = (uStage - thresh) * vWet;   // same effective threshold as vWet
  vUv = aCellUv;
  vec3 p = position;
  p.y = aElev;
  float sx = aSlope.x;
  float sz = aSlope.y;
  float ny = sqrt(max(0.0, 10000.0 - sx * sx - sz * sz));
  vNormalW = normalize(vec3(sx, ny, sz));
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`,
    fragmentShader: FS_TERRAIN,
  });
}

export function makeWaterMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uStage: { value: 0 },
      uBlock: { value: 1 },
      uTime: { value: 0 },
      uFogCol: { value: new THREE.Color("#1d211e") },
      uFogD: { value: 0.000045 },
    },
    vertexShader: /* glsl */`
attribute float aElev;
attribute float aThresh;
attribute float aOut;
attribute float aSettle;
attribute vec2 aCellUv;
uniform float uStage;
uniform float uBlock;
uniform float uTime;
varying vec3 vWorld;
varying float vDepth;
varying vec2 vUv;
void main() {
  float block = mix(uBlock, 1.0, step(0.5, aSettle));
  float thresh = aThresh * block;
  float sub = thresh <= uStage ? 1.0 : 0.0;
  // Surface from the EFFECTIVE (blockage-adjusted) threshold, so the surface,
  // the depth and the wet test all agree. Identical to aOut + uStage when
  // uBlock == 1, because aOut == aElev - aThresh.
  float surf = aElev - thresh + uStage;
  vDepth = (surf - aElev) * sub;
  vUv = aCellUv;
  vec3 p = position;
  float wob = (sin(uTime * 1.6 + p.x * 0.031) + sin(uTime * 0.9 - p.z * 0.023)) * 0.045;
  // Dry vertices now sit ON the terrain instead of 90 km below it. The fragment
  // shader discards them (vDepth == 0), and shoreline triangles taper cleanly to
  // the waterline instead of stretching into shards: the old sink was
  // -90000 * scale.y(2.0) = -180000, past the camera's 160000 far plane.
  p.y = surf * sub + wob * sub + aElev * (1.0 - sub);
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`,
    fragmentShader: /* glsl */`
uniform float uTime;
uniform vec3 uFogCol;
uniform float uFogD;
varying vec3 vWorld;
varying float vDepth;
varying vec2 vUv;
${FOG}
void main() {
  if (vDepth <= 0.0001) discard;
  float d = min(vDepth, 3.0);
  float glint = 0.5 + 0.5 * sin(vWorld.x * 0.14 + uTime * 2.1) * sin(vWorld.z * 0.12 - uTime * 1.6);
  vec3 toneA = vec3(0.42, 0.60, 0.62);
  vec3 toneB = vec3(0.09, 0.24, 0.36);
  vec3 col = mix(toneA, toneB, smoothstep(0.12, 2.1, d));
  col += glint * 0.05;
  float edge = 1.0 - smoothstep(0.0, 0.30, vDepth);
  col = mix(col, vec3(0.85, 0.94, 0.95), edge * 0.75);
  float alpha = 0.52 + 0.44 * smoothstep(0.0, 0.5, d);
  gl_FragColor = vec4(applyFog(col, length(vWorld - cameraPosition), uFogCol, uFogD), alpha);
}`,
    transparent: true,
    depthWrite: false,
  });
}

export function makeBuildingsMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uStage: { value: 0 },
      uBlock: { value: 1 },
      uFogCol: { value: new THREE.Color("#1d211e") },
      uFogD: { value: 0.000045 },
      uAmb: { value: new THREE.Vector3(1.0, 0.97, 0.9) },
      uFlat: { value: 0 },
    },
    vertexShader: /* glsl */`
attribute vec3 iPos;      // x, z, rot(rad)
attribute vec4 iDim;      // w, l, h(m, already in meters), class
attribute vec3 iHand;     // thresh, out, elev (meters)
uniform float uStage;
uniform float uBlock;
uniform float uFlat;
varying vec3 vNormalW;
varying vec3 vWorld;
varying float vClass;
varying float vWet;
varying float vDepth;
varying float vH;
void main() {
  float block = mix(uBlock, 1.0, step(0.5, iDim.w));
  float thresh = iHand.x * block;
  vWet = step(thresh, uStage);
  vDepth = max(0.0, uStage - thresh) * vWet;   // was iHand.y + uStage - iHand.z: ignored blockage
  vClass = iDim.w;
  vH = iDim.z;
  float co = cos(iPos.z), si = sin(iPos.z);
  vec3 scaled = vec3(position.x * iDim.x,
                     (position.y + 0.5) * iDim.z * (1.0 - 0.90 * uFlat),
                     position.z * iDim.y);
  vec3 rr = vec3(co * scaled.x + si * scaled.z, scaled.y, -si * scaled.x + co * scaled.z);
  // iPos is (x, z, rot) — iPos.y is the NORTH coordinate, not a height. Adding it
  // to the elevation threw every building vertically by its own z (±16 km on this
  // site), scattering the whole city layer out of frame. Base height is iHand.z.
  vec3 p = rr + vec3(iPos.x, iHand.z, iPos.y);
  vec3 n = normal;
  vNormalW = normalize(vec3(co * n.x + si * n.z, n.y, -si * n.x + co * n.z));
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`,
    fragmentShader: /* glsl */`
uniform vec3 uAmb;
uniform vec3 uFogCol;
uniform float uFogD;
varying vec3 vNormalW;
varying vec3 vWorld;
varying float vClass;
varying float vWet;
varying float vDepth;
varying float vH;
${FOG}
void main() {
  vec3 wall = vClass < 0.5
      ? vec3(0.74, 0.44, 0.29) * mix(0.9, 1.1, fract(vH * 7.31))
      : vec3(0.82, 0.80, 0.75);
  float sun = max(dot(normalize(vNormalW), normalize(vec3(-0.55, 0.62, 0.45))), 0.0);
  float skyl = 0.35 + 0.30 * (vNormalW.y * 0.5 + 0.5);
  vec3 col = wall * (skyl * uAmb + sun * vec3(0.9, 0.8, 0.6));
  col = clamp(col * 0.92, 0.0, 1.0);
  if (vWet > 0.5) {
    float d = min(vDepth, 3.0);
    vec3 wet = mix(vec3(0.40, 0.54, 0.58), vec3(0.10, 0.25, 0.35), smoothstep(0.12, 2.0, d));
    // flood climbs the walls: lower part tinted, proportion to depth vs building height
    float cover = clamp(d / max(0.6, vH), 0.0, 1.0);
    cover *= smoothstep(0.0, 0.35, d);
    col = mix(col, wet, 0.35 + 0.55 * cover);
  }
  gl_FragColor = vec4(applyFog(col, length(vWorld - cameraPosition), uFogCol, uFogD), 1.0);
}`,
  });
}

export function makeLineMaterial({ col = "#9aa6a0", wet = "#e2573f", opacity = 1 } = {}) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uStage: { value: 0 },
      uCol: { value: new THREE.Color(col) },
      uWetCol: { value: new THREE.Color(wet) },
      uFogCol: { value: new THREE.Color("#1d211e") },
      uFogD: { value: 0.000045 },
      uOpacity: { value: opacity },
    },
    vertexShader: /* glsl */`
attribute float aY;     // base elevation for this vertex
attribute vec3 aF;      // thresh, out, class
uniform float uStage;
varying vec3 vWorld;
varying float vWet;
varying float vClass;
void main() {
  vClass = aF.z;
  vWet = step(aF.x, uStage);
  vec3 p = position;
  p.y = aY;
  if (vWet > 0.5) p.y = max(aY, aF.y + uStage) + 0.5;
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`,
    fragmentShader: /* glsl */`
uniform vec3 uCol;
uniform vec3 uWetCol;
uniform vec3 uFogCol;
uniform float uFogD;
uniform float uOpacity;
varying vec3 vWorld;
varying float vWet;
varying float vClass;
${FOG}
void main() {
  vec3 col = mix(uCol, uWetCol, vWet);
  gl_FragColor = vec4(applyFog(col, length(vWorld - cameraPosition), uFogCol, uFogD), uOpacity);
}`,
    transparent: opacity < 1.0,
    depthWrite: opacity >= 1.0,
  });
}

// marker points (shelters / facilities / no-go splats)
export function makeMarkerMaterial({ tint } = {}) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uStage: { value: 0 },
      uTint: { value: new THREE.Color(tint) },
      uPxScale: { value: 700 },   // = viewportH / (2·tan(fov/2)); set per resize
      uTime: { value: 0 },
    },
    vertexShader: /* glsl */`
attribute vec4 aM;      // thresh(m), kind, worldDiameter(m), seen(0/1)
uniform float uStage;
uniform float uPxScale;
varying float vRisk;
varying float vKind;
varying float vSeen;
void main() {
  vRisk = step(aM.x, uStage);
  vKind = aM.y;
  vSeen = aM.w;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float grow = vKind > 1.5 ? (1.0 + 0.35 * vRisk) : (0.9 + 0.25 * vRisk);
  gl_PointSize = clamp(aM.z * grow * uPxScale / max(60.0, -mv.z), 2.0, 720.0);
}`,
    fragmentShader: /* glsl */`
uniform vec3 uTint;
uniform float uTime;
varying float vRisk;
varying float vKind;
varying float vSeen;
void main() {
  if (vSeen < 0.5) discard;
  vec2 d = gl_PointCoord - vec2(0.5);
  float r = length(d) * 2.0;
  if (r > 1.0) discard;
  float a;
  vec3 col = uTint;
  if (vKind > 2.5) {                      // 3 building dot (slab)
    col = mix(uTint, vec3(0.10, 0.44, 0.52), vRisk * 0.85);
    a = (1.0 - smoothstep(0.42, 0.98, r)) * 0.62;
  } else if (vKind > 1.5) {               // 2 no-go splat: soft halo
    float pulse = 0.85 + 0.15 * sin(uTime * 1.9);
    a = (1.0 - smoothstep(0.0, 1.0, r)) * 0.30 * pulse * (0.25 + vRisk);
    col = vec3(0.88, 0.28, 0.18);
  } else if (vKind > 0.5) {               // 1 shelter: disc + ring, active pulse
    float pulse = 0.62 + 0.30 * sin(uTime * 2.4);
    a = (1.0 - smoothstep(0.5, 0.92, r)) * 0.24 * pulse
      + smoothstep(0.62, 0.70, r) * (1.0 - smoothstep(0.78, 1.0, r)) * 0.95 * pulse;
    col = mix(uTint, vec3(0.30, 0.85, 0.60), 0.7);
  } else {                                // 0 facility: crisp disc
    a = (1.0 - smoothstep(0.55, 0.95, r)) * 0.85;
    if (vRisk > 0.5) col = vec3(0.93, 0.30, 0.24);
  }
  gl_FragColor = vec4(col, a);
}`,
    transparent: true,
    depthWrite: false,
  });
}

// exploded-view slab materials: single ShaderMaterial parameterized by uMode
export function makeSlabMaterial() {
  const VERT = /* glsl */`
attribute float aElev;
attribute float aThresh;
attribute float aOut;
attribute float aSettle;
attribute vec2 aCellUv;
uniform float uStage;
uniform float uBlock;
varying vec3 vWorld;
varying vec2 vUv;
varying float vDepth;
varying float vHand;
varying float vWet;
void main() {
  float block = mix(uBlock, 1.0, step(0.5, aSettle));
  vWet = step(aThresh * block, uStage);
  vHand = aThresh;
  // was (aOut + uStage - aElev): that is uStage - aThresh, the UNADJUSTED
  // threshold, while vWet above uses aThresh * block. Under the seasonal (0.88)
  // and El Niño (0.62) scenarios the extra cells passed the wet test but came out
  // with negative depth, so the exploded flood slab disagreed with the main view.
  vDepth = (uStage - aThresh * block) * (uStage > 0.0 ? 1.0 : 0.0);
  vec3 p = position;
  p.y = 0.0;                       // slabs are flat planes
  vUv = aCellUv;
  vec4 wp = modelMatrix * vec4(p, 1.0);
  vWorld = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
  const FRAG = /* glsl */`
uniform int uMode;         // 0 relief, 1 drainage, 2 hand heat, 3 flood, 4 blocks, 5 response
uniform float uStage;
varying vec3 vWorld;
varying vec2 vUv;
varying float vDepth;
varying float vHand;
varying float vWet;
float hash21(vec2 p) {
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}
void main() {
  vec3 col;
  if (uMode == 0) {
    float t = hash21(floor(vUv * 240.0));
    col = mix(vec3(0.24, 0.28, 0.24), vec3(0.52, 0.48, 0.36), 0.4 + 0.5 * t);
  } else if (uMode == 1) {
    float e = 1.0 - smoothstep(0.0, 14.0, vHand);
    col = mix(vec3(0.10, 0.11, 0.12), vec3(0.55, 0.75, 0.70), pow(e, 1.6));
  } else if (uMode == 2) {
    float t = clamp(vHand / 9.0, 0.0, 1.0);
    vec3 a = mix(vec3(0.75, 0.12, 0.10), vec3(0.93, 0.60, 0.14), smoothstep(0.0, 0.3, t));
    vec3 b = mix(a, vec3(0.55, 0.78, 0.70), smoothstep(0.22, 0.52, t));
    col = mix(b, vec3(0.88, 0.91, 0.86), smoothstep(0.5, 0.92, t));
  } else if (uMode == 3) {
    col = vec3(0.16, 0.19, 0.22);
    if (vWet > 0.5) {
      float d = min(vDepth, 3.0);
      col = mix(vec3(0.42, 0.60, 0.62), vec3(0.09, 0.24, 0.36), smoothstep(0.12, 2.1, d));
    }
  } else if (uMode == 4) {
    col = vec3(0.65, 0.42, 0.30);
    if (vWet > 0.5) col = mix(col, vec3(0.10, 0.45, 0.55), 0.75);
  } else {
    col = vec3(0.2, 0.24, 0.22);
    if (vWet > 0.5) col = vec3(0.82, 0.31, 0.26);
  }
  gl_FragColor = vec4(col, 1.0);
}`;
  return new THREE.ShaderMaterial({ uniforms: { uMode: { value: 0 }, uStage: { value: 0 }, uBlock: { value: 1 } }, vertexShader: VERT, fragmentShader: FRAG });
}
