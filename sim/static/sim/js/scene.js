// Renderer, camera rig, sky/lighting, resize plumbing.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const SKY_TOP = { lab: "#0d1a22", studio: "#dfe6ea" };
const SKY_HOR = { lab: "#8a5a22", studio: "#eef1f2" };
const FOGC = "#232a26";
const FOGD = 0.000045;

export class Viewer {
  constructor(host) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.setSize(host.clientWidth, host.clientHeight);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(SKY_TOP.lab);
    this.scene.fog = new THREE.FogExp2(new THREE.Color(FOGC), FOGD);

    this.camera = new THREE.PerspectiveCamera(34, host.clientWidth / host.clientHeight, 3, 160000);
    this.scene.add(this.camera);

    // gradient sky dome + soft horizon haze (original palette; dusk savanna)
    const skyGeo = new THREE.SphereGeometry(70000, 24, 12);
    this.skyMat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        top: { value: new THREE.Color(SKY_TOP.lab) },
        hor: { value: new THREE.Color(SKY_HOR.lab) },
        mixA: { value: 0 },
      },
      vertexShader: /* glsl */`
        varying vec3 vP;
        void main() {
          vP = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: /* glsl */`
        uniform vec3 top;
        uniform vec3 hor;
        uniform float mixA;
        varying vec3 vP;
        void main() {
          float h = clamp(normalize(vP).y * 1.4 + 0.24, 0.0, 1.0);
          vec3 c = mix(hor, top, pow(h, 0.65));
          gl_FragColor = vec4(c, 1.0);
        }`,
    });
    this.sky = new THREE.Mesh(skyGeo, this.skyMat);
    this.sky.frustumCulled = false;
    this.scene.add(this.sky);

    // (custom shaders carry their own light math; these exist for plain meshes)
    const sun = new THREE.DirectionalLight(0xffd9a8, 1.6);
    sun.position.set(-0.75, 0.55, 0.35).multiplyScalar(40000);
    this.scene.add(sun);
    this.scene.add(new THREE.HemisphereLight(0x9fb8c8, 0x40382c, 0.5));

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.rotateSpeed = 0.85;
    this.controls.maxPolarAngle = Math.PI * 0.492;
    this.controls.minDistance = 220;
    this.controls.maxDistance = 68000;

    this.clock = new THREE.Clock();
    this.markerMats = [];
    this.onResize();
    window.addEventListener("resize", () => this.onResize());
  }

  onResize() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const px = h / (2 * Math.tan((this.camera.fov * Math.PI) / 360));
    for (const m of this.markerMats) if (m.uniforms?.uPxScale) m.uniforms.uPxScale.value = px;
  }

  setMode(view) {
    const top = new THREE.Color(view === "studio" ? SKY_TOP.studio : SKY_TOP.lab);
    const hor = new THREE.Color(view === "studio" ? SKY_HOR.studio : SKY_HOR.lab);
    this.skyMat.uniforms.top.value.copy(top);
    this.skyMat.uniforms.hor.value.copy(view === "studio" ? new THREE.Color("#d8dee1") : hor);
    this.scene.background = view === "studio" ? top : this.scene.background;
    this.renderer.toneMappingExposure = view === "studio" ? 1.0 : 1.05;
    this.scene.fog.color.copy(new THREE.Color(view === "studio" ? "#d9dfdd" : FOGC));
    this.scene.fog.density = view === "studio" ? 0.000030 : FOGD;
    this.skyMat.uniforms.mixA.value = view === "studio" ? 1 : 0;
    for (const m of this.markerMats) if (m.uniforms?.uPxScale != null) this.onResize();
  }

  registerMarkers(mats) {
    this.markerMats = mats.filter(Boolean);
    this.onResize();
  }

  render(t) {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  dispose() { /* handled by removal of layers; renderer persists across site swaps */ }
}
