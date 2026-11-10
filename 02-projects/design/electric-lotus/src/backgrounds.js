/* 电莲花 · 四套车展风格背景灯光 rig（全程序化，无外部资源）
 *
 * 交付物 2：
 *  - BACKGROUND_NAMES
 *  - applyBackground(scene, name, renderer?) → { name, dispose() }
 *    切换整套环境：移除旧 rig（userData.rigTag==='bg'）→ 加新 rig Group →
 *    设 scene.background / scene.fog → 用 PMREMGenerator.fromScene(envScene)
 *    生成环境贴图赋给 scene.environment（销毁旧 PMREM 纹理）。
 *
 * 顶层无 DOM / WebGL 访问（PMREM / canvas 都在函数内），可被 node 直接 import。
 * renderer 解析顺序：显式参数 → setRenderer() 存储 → scene.userData.renderer
 *                  → window.__electricLotus.renderer（接线层全局）。都没有则跳过
 *    环境贴图（仅保留 rig 与背景），不抛错。
 */
import * as THREE from "three";

export const BACKGROUND_NAMES = ["auto_show", "wind_tunnel", "studio", "night_road"];

const RIG_TAG = "bg";

let _renderer = null;
let _pmrem = null;
let _pmremFor = null;
let _current = null; // { name, envRT, dispose() }

/** 由接线层（main.js）在初始化后调用一次，此后 applyBackground(scene,name) 即可。 */
export function setRenderer(r) {
  _renderer = r || null;
}

function resolveRenderer(scene, explicit) {
  if (explicit) return explicit;
  if (_renderer) return _renderer;
  if (scene && scene.userData && scene.userData.renderer) return scene.userData.renderer;
  if (typeof window !== "undefined" && window.__electricLotus && window.__electricLotus.renderer) {
    return window.__electricLotus.renderer;
  }
  return null;
}

/* ------------------------------------------------------------------ *
 * 资源释放
 * ------------------------------------------------------------------ */
function disposeMaterial(m) {
  if (!m) return;
  for (const k in m) {
    const v = m[k];
    if (v && v.isTexture) v.dispose();
  }
  if (m.uniforms) {
    for (const k in m.uniforms) {
      const u = m.uniforms[k];
      if (u && u.value && u.value.isTexture) u.value.dispose();
    }
  }
  m.dispose();
}

function disposeObject(root) {
  if (!root) return;
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const mat = o.material;
    if (Array.isArray(mat)) mat.forEach(disposeMaterial);
    else disposeMaterial(mat);
  });
}

/** 移除并释放场景内所有 rigTag==='bg' 的顶层对象（含其子树）。 */
function sweepRig(scene) {
  const tagged = [];
  scene.traverse((o) => { if (o.userData && o.userData.rigTag === RIG_TAG) tagged.push(o); });
  const set = new Set(tagged);
  for (const o of tagged) {
    let p = o.parent, hasTaggedAncestor = false;
    while (p) { if (set.has(p)) { hasTaggedAncestor = true; break; } p = p.parent; }
    if (!hasTaggedAncestor) {
      if (o.parent) o.parent.remove(o);
      disposeObject(o);
    }
  }
}

/* ------------------------------------------------------------------ *
 * 材质 / 几何小工具
 * ------------------------------------------------------------------ */
function standard(hex, roughness, metalness, envInt = 1.0) {
  return new THREE.MeshStandardMaterial({ color: hex, roughness, metalness, envMapIntensity: envInt });
}
function glow(hex, fog = true) {
  return new THREE.MeshBasicMaterial({ color: hex, fog });
}
function glowRGB(r, g, b, fog = true) {
  const m = new THREE.MeshBasicMaterial({ fog });
  m.color.setRGB(r, g, b); // 线性工作空间，可 >1 供 PMREM 捕获 HDR
  return m;
}

function gradientSphere(topHex, botHex, radius) {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { uTop: { value: new THREE.Color(topHex) }, uBot: { value: new THREE.Color(botHex) } },
    vertexShader: /* glsl */`
      varying vec3 vP;
      void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: /* glsl */`
      varying vec3 vP; uniform vec3 uTop; uniform vec3 uBot;
      void main(){
        float h = normalize(vP).y * 0.5 + 0.5;
        vec3 c = mix(uBot, uTop, smoothstep(0.0, 1.0, h));
        gl_FragColor = vec4(c, 1.0);
      }`,
  });
  return new THREE.Mesh(new THREE.SphereGeometry(radius, 32, 16), mat);
}

/** 从光源到地面的可见光锥：shader 实现轮廓 fresnel 柔化 + 沿程衰减（写实体积光，非硬边几何）。 */
function lightShaft(hex, from, to, rFloor, opacity) {
  const a = new THREE.Vector3().fromArray(from);
  const b = new THREE.Vector3().fromArray(to);
  const dir = new THREE.Vector3().subVectors(a, b); // 底→顶（顶=灯）
  const len = dir.length();
  const geo = new THREE.ConeGeometry(rFloor, len, 32, 1, true);
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending, fog: false,
    uniforms: {
      uColor: { value: new THREE.Color(hex) },
      uOpacity: { value: opacity },
      uLen: { value: len },
    },
    vertexShader: /* glsl */`
      varying vec3 vN; varying vec3 vV; varying float vT;
      uniform float uLen;
      void main(){
        vT = clamp(position.y / uLen + 0.5, 0.0, 1.0);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */`
      varying vec3 vN; varying vec3 vV; varying float vT;
      uniform vec3 uColor; uniform float uOpacity;
      void main(){
        float edge = pow(abs(dot(normalize(vN), normalize(vV))), 1.5);
        float lenFade = smoothstep(0.0, 0.3, vT);
        float a = uOpacity * edge * lenFade;
        gl_FragColor = vec4(uColor, a);
      }`,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  return mesh;
}

/** 径向接触阴影贴地，弥补不开阴影贴图的接地感。 */
function contactShadow(radius, y) {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(128, 128, 8, 128, 128, 124);
  g.addColorStop(0, "rgba(0,0,0,0.55)");
  g.addColorStop(0.5, "rgba(0,0,0,0.28)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, fog: false });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(radius * 2, radius * 2), mat);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = y;
  return mesh;
}

function gridTexture(hex, divisions, lineW) {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, 512, 512);
  ctx.strokeStyle = hex;
  ctx.lineWidth = lineW;
  const step = 512 / divisions;
  for (let i = 0; i <= divisions; i++) {
    const p = Math.round(i * step) + 0.5;
    ctx.beginPath(); ctx.moveTo(p, 0); ctx.lineTo(p, 512); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, p); ctx.lineTo(512, p); ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function envRoom(hex) {
  const m = new THREE.Mesh(
    new THREE.BoxGeometry(60, 40, 60),
    new THREE.MeshBasicMaterial({ color: hex, side: THREE.BackSide, fog: false }),
  );
  return m;
}
function envPanel(w, h, rgb, pos) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), glowRGB(rgb[0], rgb[1], rgb[2], false));
  mesh.position.set(pos[0], pos[1], pos[2]);
  mesh.lookAt(0, 0, 0);
  return mesh;
}
function makeEnvScene(panels) {
  const es = new THREE.Scene();
  es.add(envRoom(panels.room));
  for (const p of panels.list) es.add(envPanel(p.w, p.h, p.rgb, p.pos));
  return es;
}

function tagRig(g) {
  g.userData.rigTag = RIG_TAG;
  return g;
}
function addTaggedLight(g, light) {
  light.userData.rigTag = RIG_TAG;
  g.add(light);
  if (light.target) { light.target.userData.rigTag = RIG_TAG; g.add(light.target); }
  return light;
}

/* ================================================================== *
 * auto_show —— 车展展台
 * ================================================================== */
function buildAutoShow() {
  const g = tagRig(new THREE.Group());

  // 地面 + 转盘（顶面 y=0，略高于地面）
  const floor = new THREE.Mesh(new THREE.CircleGeometry(34, 64), standard(0x0b0d12, 0.5, 0.25, 0.8));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.05; g.add(floor);
  const plat = new THREE.Mesh(new THREE.CylinderGeometry(4.3, 4.35, 0.1, 72), standard(0x14171d, 0.15, 0.5, 1.1));
  plat.position.y = -0.05; g.add(plat);
  // 转盘边缘微光环（低调，非霓虹）
  const edge = new THREE.Mesh(new THREE.TorusGeometry(4.32, 0.015, 8, 120), glowRGB(0.5, 0.34, 0.16, false));
  edge.rotation.x = Math.PI / 2; edge.position.y = 0.005; g.add(edge);
  g.add(contactShadow(3.4, 0.011));

  // 背景墙 + 微光品牌带（柔和点亮的招牌，非发光色块）
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(60, 26), standard(0x090a0e, 0.85, 0.1, 0.6));
  wall.position.set(0, 11, -18); g.add(wall);
  const band = new THREE.Mesh(new THREE.BoxGeometry(34, 1.1, 0.2), glowRGB(0.75, 0.5, 0.24, false));
  band.position.set(0, 6.2, -17.7); g.add(band);

  // 头顶射灯环（6 灯 + 可见光锥）+ 暖主光 / 冷轮廓光
  const ring = 6;
  for (let i = 0; i < ring; i++) {
    const ang = (i / ring) * Math.PI * 2;
    const x = Math.cos(ang) * 5.4, z = Math.sin(ang) * 5.4;
    const warm = i % 2 === 0;
    const col = warm ? 0xffe9c8 : 0xcfe2ff;
    const pos = [x, 8.5, z];
    const spot = new THREE.SpotLight(col, 130, 42, 0.42, 0.55, 1.5);
    spot.position.set(x, 8.5, z);
    spot.target.position.set(0, 0, 0);
    addTaggedLight(g, spot);
    g.add(lightShaft(col, pos, [x * 0.5, 0.0, z * 0.5], 1.7, 0.11));
  }
  const key = addTaggedLight(g, new THREE.DirectionalLight(0xffe6c4, 2.4));
  key.position.set(7, 9, 6);
  const rim = addTaggedLight(g, new THREE.DirectionalLight(0x8fb8ff, 1.7));
  rim.position.set(-7, 7, -7);
  g.add(new THREE.AmbientLight(0x30363f, 0.6));

  const envScene = makeEnvScene({
    room: 0x07080c,
    list: [
      { w: 34, h: 34, rgb: [2.6, 2.4, 2.1], pos: [0, 16, 0] },           // 顶部大光
      { w: 10, h: 6, rgb: [3.0, 2.0, 1.0], pos: [14, 7, 8] },            // 暖侧
      { w: 10, h: 6, rgb: [1.0, 1.6, 3.0], pos: [-14, 7, -8] },          // 冷侧
      { w: 30, h: 3, rgb: [1.6, 1.0, 0.5], pos: [0, 5, -18] },           // 品牌带反射
    ],
  });

  return {
    group: g,
    background: new THREE.Color(0x0a0c10),
    fog: new THREE.Fog(0x0a0c10, 22, 95),
    envScene,
  };
}

/* ================================================================== *
 * wind_tunnel —— 深夜风洞
 * ================================================================== */
function buildWindTunnel() {
  const g = tagRig(new THREE.Group());

  // 工业测试设施：中性冷灰钢墙（低饱和，非钢蓝霓虹）
  const wallMat = standard(0x171b20, 0.72, 0.45, 0.7);
  const wallL = new THREE.Mesh(new THREE.PlaneGeometry(60, 16), wallMat);
  wallL.position.set(-9, 8, 0); wallL.rotation.y = Math.PI / 2; g.add(wallL);
  const wallR = new THREE.Mesh(new THREE.PlaneGeometry(60, 16), wallMat);
  wallR.position.set(9, 8, 0); wallR.rotation.y = -Math.PI / 2; g.add(wallR);
  const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(18, 60), standard(0x14171b, 0.8, 0.35, 0.6));
  ceiling.position.set(0, 16, 0); ceiling.rotation.x = Math.PI / 2; g.add(ceiling);

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(20, 60), standard(0x191d22, 0.6, 0.5, 0.9));
  floor.rotation.x = -Math.PI / 2; g.add(floor);

  // 地面标线网格：极淡冷白（测试地坪漆线），普通混合非 additive，杜绝霓虹感
  const gtex = gridTexture("#9fb0bf", 30, 1.5);
  gtex.repeat.set(4, 10);
  const grid = new THREE.Mesh(
    new THREE.PlaneGeometry(20, 60),
    new THREE.MeshBasicMaterial({ map: gtex, transparent: true, opacity: 0.16, depthWrite: false, fog: true }),
  );
  grid.rotation.x = -Math.PI / 2; grid.position.y = 0.012; g.add(grid);
  g.add(contactShadow(3.2, 0.02));

  // 沿墙长条荧光灯带：冷白线性灯具（真实设施），非饱和青
  const stripMat = glowRGB(1.7, 1.82, 1.95, false);
  for (const x of [-8.7, 8.7]) {
    for (const y of [2.5, 6, 9.5, 13]) {
      const strip = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.3, 54), stripMat);
      strip.position.set(x, y, 0); g.add(strip);
    }
  }

  // 冷白主光 + 中性补光（写实曝光，低饱和）
  const key = addTaggedLight(g, new THREE.DirectionalLight(0xdfeaf5, 2.6));
  key.position.set(-7, 9, -9);
  const fill = addTaggedLight(g, new THREE.DirectionalLight(0xbcc8d4, 1.1));
  fill.position.set(6, 10, 8);
  g.add(new THREE.AmbientLight(0x222830, 1.15));

  const envScene = makeEnvScene({
    room: 0x1e242b,
    list: [
      { w: 3, h: 44, rgb: [2.4, 2.55, 2.7], pos: [-9, 7, 0] },
      { w: 3, h: 44, rgb: [2.4, 2.55, 2.7], pos: [9, 7, 0] },
      { w: 16, h: 16, rgb: [2.0, 2.1, 2.25], pos: [0, 16, 0] },
      { w: 20, h: 3, rgb: [1.7, 1.8, 1.95], pos: [0, 1, -20] },
    ],
  });

  return {
    group: g,
    background: new THREE.Color(0x171c22),
    fog: new THREE.Fog(0x171c22, 16, 74),
    envScene,
  };
}

/* ================================================================== *
 * studio —— 纯白摄影棚
 * ================================================================== */
function buildStudio() {
  const g = tagRig(new THREE.Group());

  // 白色地面 + 渐变天幕（cyclorama）
  const floor = new THREE.Mesh(new THREE.CircleGeometry(40, 64), standard(0xf1f2f4, 0.95, 0.0, 1.0));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.02; g.add(floor);
  const sky = gradientSphere(0xffffff, 0xdde1e6, 70);
  g.add(sky);
  g.add(contactShadow(3.2, 0.0));

  // 半球柔光 + 两盏柔和方向光
  const hemi = addTaggedLight(g, new THREE.HemisphereLight(0xffffff, 0xcfd4da, 1.1));
  const key = addTaggedLight(g, new THREE.DirectionalLight(0xffffff, 2.0));
  key.position.set(6, 12, 8);
  const fill = addTaggedLight(g, new THREE.DirectionalLight(0xf2f6ff, 1.2));
  fill.position.set(-8, 8, -6);

  const envScene = makeEnvScene({
    room: 0xf4f5f7,
    list: [
      { w: 40, h: 40, rgb: [2.8, 2.8, 2.8], pos: [0, 18, 0] },   // 顶柔光箱
      { w: 24, h: 20, rgb: [2.4, 2.4, 2.5], pos: [20, 8, 6] },   // 右
      { w: 24, h: 20, rgb: [2.3, 2.3, 2.4], pos: [-20, 8, -6] }, // 左
      { w: 30, h: 14, rgb: [2.0, 2.0, 2.1], pos: [0, 6, -22] },  // 后
    ],
  });

  return {
    group: g,
    background: new THREE.Color(0xf2f3f5),
    fog: null,
    envScene,
  };
}

/* ================================================================== *
 * night_road —— 山路夜景
 * ================================================================== */
function buildNightRoad() {
  const g = tagRig(new THREE.Group());

  // 深夜渐变天幕 + 稀疏星点 + 远山剪影
  const sky = gradientSphere(0x03050e, 0x0a1224, 300);
  g.add(sky);

  const starCount = 420;
  const pos = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i++) {
    const u = Math.random(), v = Math.random() * 0.62 + 0.05; // 偏上半球
    const theta = u * Math.PI * 2, phi = Math.acos(1 - 2 * v);
    const r = 240;
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = Math.abs(r * Math.cos(phi)) + 8;
    pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({
    color: 0xdfe8ff, size: 1.6, sizeAttenuation: false, fog: false, transparent: true, opacity: 0.9,
  }));
  g.add(stars);

  const hillMat = standard(0x05070d, 1.0, 0.0, 0.2);
  for (const [hx, hz, s] of [[-60, -80, 34], [40, -95, 44], [90, -60, 30], [-100, -40, 26]]) {
    const hill = new THREE.Mesh(new THREE.ConeGeometry(s, s * 0.5, 5), hillMat);
    hill.position.set(hx, s * 0.22, hz);
    hill.rotation.y = Math.random() * Math.PI;
    g.add(hill);
  }

  // 沥青路面（略湿，反射灯光）
  const road = new THREE.Mesh(new THREE.PlaneGeometry(14, 120), standard(0x0b0d11, 0.55, 0.35, 1.0));
  road.rotation.x = -Math.PI / 2; g.add(road);
  const verge = new THREE.Mesh(new THREE.PlaneGeometry(160, 160), standard(0x070910, 1.0, 0.0, 0.4));
  verge.rotation.x = -Math.PI / 2; verge.position.y = -0.03; g.add(verge);
  g.add(contactShadow(3.2, 0.011));

  // 钠蒸汽路灯：灯杆 + 暖发光灯头 + 向下光池
  const postMat = standard(0x14161b, 0.6, 0.7, 0.8);
  const headMat = glowRGB(3.0, 2.0, 1.0, false);
  for (const lx of [-14, -5, 5, 14]) {
    const z = 7;
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 6, 8), postMat);
    post.position.set(lx, 3, z); g.add(post);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.3, 12, 8), headMat);
    head.position.set(lx, 6, z - 0.6); g.add(head);
    const spot = new THREE.SpotLight(0xffb45a, 160, 26, 0.62, 0.6, 2);
    spot.position.set(lx, 6, z - 0.6);
    spot.target.position.set(lx, 0, z - 3);
    addTaggedLight(g, spot);
  }

  // 月色冷轮廓 + 极低环境光
  const moon = addTaggedLight(g, new THREE.DirectionalLight(0x9fb8e6, 0.7));
  moon.position.set(-20, 26, -18);
  g.add(new THREE.AmbientLight(0x0a1220, 0.7));

  const envScene = makeEnvScene({
    room: 0x04060c,
    list: [
      { w: 4, h: 4, rgb: [3.2, 2.1, 1.0], pos: [-14, 6, 6] },
      { w: 4, h: 4, rgb: [3.2, 2.1, 1.0], pos: [14, 6, 6] },
      { w: 4, h: 4, rgb: [2.8, 1.9, 0.9], pos: [0, 6, 6] },
      { w: 16, h: 16, rgb: [0.5, 0.7, 1.3], pos: [-24, 26, -20] }, // 月
      { w: 40, h: 6, rgb: [0.2, 0.28, 0.5], pos: [0, 3, -26] },     // 地平线微光
    ],
  });

  return {
    group: g,
    background: new THREE.Color(0x04060c),
    fog: new THREE.Fog(0x070a14, 30, 170),
    envScene,
  };
}

const BUILDERS = {
  auto_show: buildAutoShow,
  wind_tunnel: buildWindTunnel,
  studio: buildStudio,
  night_road: buildNightRoad,
};

/* ------------------------------------------------------------------ *
 * PMREM 环境贴图
 * ------------------------------------------------------------------ */
function buildEnvTexture(renderer, envScene) {
  if (!renderer) { disposeObject(envScene); return null; }
  if (!_pmrem || _pmremFor !== renderer) {
    if (_pmrem) _pmrem.dispose();
    _pmrem = new THREE.PMREMGenerator(renderer);
    _pmremFor = renderer;
  }
  try {
    const rt = _pmrem.fromScene(envScene, 0.04);
    return rt;
  } catch (e) {
    console.warn("[backgrounds] PMREM generation failed:", e);
    return null;
  } finally {
    disposeObject(envScene); // envScene 是一次性的，生成后即释放
  }
}

/* ------------------------------------------------------------------ *
 * applyBackground
 * ------------------------------------------------------------------ */
export function applyBackground(scene, name, renderer) {
  if (!BUILDERS[name]) name = BACKGROUND_NAMES[0];
  const rend = resolveRenderer(scene, renderer);

  // 1) 释放旧 rig + 旧 PMREM 纹理
  if (_current) { _current.dispose(); _current = null; }
  else sweepRig(scene);

  // 2) 构建新 rig（先建后换，失败时旧环境仍在）
  const built = BUILDERS[name]();
  const envRT = buildEnvTexture(rend, built.envScene);

  // 3) 切换
  scene.add(built.group);
  scene.background = built.background;
  scene.fog = built.fog || null;
  scene.environment = envRT ? envRT.texture : null;

  const api = {
    name,
    dispose() {
      sweepRig(scene);
      if (envRT) {
        if (scene.environment === envRT.texture) scene.environment = null;
        envRT.dispose();
      }
      if (scene.fog === built.fog) scene.fog = null;
      if (scene.background === built.background) scene.background = null;
      if (_current === api) _current = null;
    },
  };
  _current = api;
  return api;
}
