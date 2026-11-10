// src/scene.js —— 渲染舞台与相机导演层
//
// initScene(container) → { renderer, scene, camera, controls,
//   setPreset, setTurntable, setPickTarget, pickPart, onFrame, resize, dispose }
//
// 合同要点:
//  - antialias、pixelRatio ≤ 2、ACESFilmicToneMapping、SRGB 输出、FOV 35
//  - setPreset(front34|side|cockpit|top) → ~1.2s 缓动相机飞行（可被打断）
//  - setTurntable(enabled, speed=0.15rad/s) 绕 Y 转 pick target
//  - pickPart(ndcX, ndcY) → partName | null（沿父链回溯 userData.partName）
//  - onFrame(cb) 每帧回调 (timeSec, deltaSec)；自动 resize；controls 带阻尼
//  - 顶层零 DOM/WebGL 触碰 → Node 可直接 import 冒烟

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

export const CAMERA_PRESETS = {
  front34: { pos: [5.6, 1.9, 4.6], target: [0, 0.6, 0] },
  side: { pos: [0.1, 1.1, 7.6], target: [0, 0.6, 0] },
  cockpit: { pos: [1.6, 2.3, 1.7], target: [0, 0.75, 0] },
  top: { pos: [0.02, 9.5, 0.02], target: [0, 0, 0] },
};

const FLIGHT_MS = 1200;
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function initScene(container) {
  const host = container || (typeof document !== "undefined" ? document.body : null);

  /* ---- 渲染器 ---- */
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min((typeof window !== "undefined" ? window.devicePixelRatio : 1) || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.style.display = "block";
  canvas.style.touchAction = "none";
  if (host && host.appendChild) host.appendChild(canvas);

  /* ---- 场景 + 默认环境（背景模块之后可整体替换） ---- */
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0e14);

  let envRT = null;
  try {
    const pmrem = new THREE.PMREMGenerator(renderer);
    envRT = pmrem.fromScene(new RoomEnvironment(), 0.04);
    scene.environment = envRT.texture;
    pmrem.dispose();
  } catch { /* 无 WebGL 上下文时（如 Node）跳过 */ }

  // 塑形三灯：主光 + 冷逆光 + 侧补光（车漆高光读得出来）
  const key = new THREE.DirectionalLight(0xfff3e2, 2.3);
  key.position.set(5.5, 8, 4.5);
  const rim = new THREE.DirectionalLight(0x9fc4ff, 1.15);
  rim.position.set(-6, 4.5, -5);
  const fill = new THREE.DirectionalLight(0xffffff, 0.45);
  fill.position.set(-3, 2.2, 6);
  scene.add(new THREE.HemisphereLight(0xcfe0ff, 0x2a2c30, 0.45), key, rim, fill);

  /* ---- 相机 + 轨道控制 ---- */
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 200);
  const D0 = CAMERA_PRESETS.front34;
  camera.position.set(...D0.pos);

  const controls = new OrbitControls(camera, canvas);
  controls.target.set(...D0.target);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 2.0;
  controls.maxDistance = 32;
  controls.maxPolarAngle = Math.PI * 0.495; // 不钻到地底

  /* ---- 相机飞行 ---- */
  let flight = null; // { t0, fromP, fromT, toP, toT }
  const tmpP = new THREE.Vector3();
  const tmpT = new THREE.Vector3();

  function setPreset(name) {
    const p = CAMERA_PRESETS[name];
    if (!p) return false;
    flight = {
      t0: (typeof performance !== "undefined" ? performance.now() : Date.now()),
      fromP: camera.position.clone(),
      fromT: controls.target.clone(),
      toP: new THREE.Vector3(...p.pos),
      toT: new THREE.Vector3(...p.target),
    };
    return true;
  }
  const cancelFlight = () => { flight = null; };
  controls.addEventListener("start", cancelFlight);

  function stepFlight(now) {
    if (!flight) return;
    const k = Math.min(1, (now - flight.t0) / FLIGHT_MS);
    const e = easeInOut(k);
    camera.position.lerpVectors(flight.fromP, flight.toP, e);
    controls.target.lerpVectors(flight.fromT, flight.toT, e);
    if (k >= 1) flight = null;
  }

  /* ---- 转盘 ---- */
  let pickTarget = null;
  let turntableOn = false;
  let turntableSpeed = 0.15;

  function setTurntable(enabled, speed) {
    turntableOn = !!enabled;
    if (typeof speed === "number" && isFinite(speed)) turntableSpeed = speed;
    return turntableOn;
  }
  function setPickTarget(obj) { pickTarget = obj || null; }

  /* ---- 拾取 ---- */
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();

  function pickPart(ndcX, ndcY) {
    if (!pickTarget) return null;
    ndc.set(ndcX, ndcY);
    raycaster.setFromCamera(ndc, camera);
    const hits = raycaster.intersectObject(pickTarget, true);
    for (const h of hits) {
      let o = h.object;
      while (o) {
        if (o.userData && o.userData.partName) return o.userData.partName;
        o = o.parent;
      }
    }
    return null;
  }

  /* ---- 帧回调 ---- */
  const frameCbs = new Set();
  function onFrame(cb) {
    if (typeof cb !== "function") return () => {};
    frameCbs.add(cb);
    return () => frameCbs.delete(cb);
  }

  /* ---- 自适应 ---- */
  function resize() {
    const w = (host && host.clientWidth) || (typeof window !== "undefined" ? window.innerWidth : 1) || 1;
    const h = (host && host.clientHeight) || (typeof window !== "undefined" ? window.innerHeight : 1) || 1;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  if (typeof window !== "undefined") window.addEventListener("resize", resize);
  let ro = null;
  if (typeof ResizeObserver !== "undefined" && host && host.nodeType === 1) {
    ro = new ResizeObserver(() => resize());
    ro.observe(host);
  }
  resize();

  /* ---- 主循环 ---- */
  let last = null;
  renderer.setAnimationLoop((ms) => {
    const now = typeof ms === "number" ? ms : (typeof performance !== "undefined" ? performance.now() : Date.now());
    const dt = last == null ? 1 / 60 : Math.min(0.1, Math.max(0, (now - last) / 1000));
    last = now;

    stepFlight(now);
    if (turntableOn && pickTarget) pickTarget.rotation.y += turntableSpeed * dt;

    for (const cb of frameCbs) {
      try { cb(now / 1000, dt); } catch (err) { console.error("[scene] onFrame 回调异常:", err); }
    }

    controls.update();
    renderer.render(scene, camera);
  });

  function dispose() {
    renderer.setAnimationLoop(null);
    if (typeof window !== "undefined") window.removeEventListener("resize", resize);
    if (ro) { try { ro.disconnect(); } catch { /* noop */ } }
    controls.removeEventListener("start", cancelFlight);
    controls.dispose();
    frameCbs.clear();
    if (envRT) envRT.dispose();
    renderer.dispose();
  }

  return {
    renderer, scene, camera, controls,
    setPreset, setTurntable, setPickTarget, pickPart, onFrame, resize, dispose,
    presets: Object.keys(CAMERA_PRESETS),
  };
}
