// src/body.js —— 电莲花楔形车身参数化建模（Theory 1 楔形 × Evija 孔隙）
//
// 合同（冻结）:
//   buildCar() → { carRoot: THREE.Group, registry: Map<string, PartInfo> }
//   PartInfo = { name, group, materialRole, explode }
//   20 个零件名固定；每个 mesh 必须带 userData.partName + userData.materialRole
//   carRoot.userData.dimensions = {length:4.5,width:2.0,height:1.15}；车轮触地 y=0
//   本文件 Node 可导入（顶层不做任何 DOM 访问）
//
// 几何方法:
//   - 分层挤出：中轴 tub（侧影挤出 ±0.56）+ 左右侧板（侧影挤出 0.56→1.00，
//     按 tuck(x) 在 plan 视图弯折 → 侧面获得真实收腰曲率）
//   - 锐边全部来自 bevel 几何；平滑法线按角度阈值自适应：端面（法线≈挤出轴）
//     保持绝对平整，bevel 段之间平滑，>阈值折角保持硬朗
//   - 面板缝隙 = 门/盖外凸 + 底下 expand 的深色 gap frame（留在车身上）
//   - 轮拱：侧板开孔（bevel 使孔口内卷成翻边）+ 内衬板（遮穿帮）+ 拱顶暗槽
//   - 文丘里侧风道：侧板开孔 + 内沉深色背板；门板上开浅内陷槽（门内衬垫底）
//   - 灯具分层：深色背板 → 发光 blade → 金属分隔 → 玻璃 lens 外罩

import * as THREE from "three";

/* ================================================================
 * 角色材质（占位；materials/paint.js 的 applyRoles 之后接管共享）
 * ================================================================ */
let _mats = null;
export function getRoleMaterials() {
  if (_mats) return _mats;
  _mats = {
    paint: new THREE.MeshStandardMaterial({
      color: 0xffb454, metalness: 0.9, roughness: 0.35, envMapIntensity: 1.2,
    }),
    glass: new THREE.MeshStandardMaterial({
      color: 0x0a0e14, transparent: true, opacity: 0.35,
      roughness: 0.1, metalness: 0.1, depthWrite: false, envMapIntensity: 1.4,
    }),
    trim: new THREE.MeshStandardMaterial({
      color: 0x14161a, roughness: 0.6, metalness: 0.1, envMapIntensity: 0.8,
    }),
    metal: new THREE.MeshStandardMaterial({
      color: 0x8a8f98, metalness: 0.9, roughness: 0.35, envMapIntensity: 1.0,
    }),
    tire: new THREE.MeshStandardMaterial({
      color: 0x0c0c0e, roughness: 0.9, metalness: 0.0, envMapIntensity: 0.5,
    }),
    light: new THREE.MeshStandardMaterial({
      color: 0x1a1408, emissive: 0xffd9a0, emissiveIntensity: 2.4,
      roughness: 0.3, metalness: 0.0,
    }),
    lightRear: new THREE.MeshStandardMaterial({
      color: 0x180604, emissive: 0xff4a3a, emissiveIntensity: 2.4,
      roughness: 0.3, metalness: 0.0,
    }),
    carbon: new THREE.MeshStandardMaterial({
      color: 0x2a2d33, metalness: 0.5, roughness: 0.4, envMapIntensity: 1.0,
    }),
  };
  return _mats;
}
// 卡钳独立材质实例（accessories.js 直接改 color，不能共享）
function newCaliperMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0xd23c2e, metalness: 0.55, roughness: 0.4, envMapIntensity: 1.0,
  });
}

/* ================================================================
 * 常量与低层几何工具
 * ================================================================ */
const HALF_W = 0.56;      // 中轴 tub 半宽（侧板内边界）
const SIDE_W = 1.00;      // 侧板外边界（车宽 2.0）
const ARCH_Y = 0.36;      // 轴心高（= 轮半径 → 触地 y=0）
const ARCH_R = 0.44;      // 轮拱半径（胎 0.36 + 间隙）
const LIP_Y = 0.20;       // 轮拱唇口高

/** plan 收腰：车头/车尾在平面图上向内收 */
function tuck(x) {
  const a = Math.min(Math.abs(x), 2.25);
  return 0.14 * (a / 2.25) ** 2;
}

/** 全局侧板弯折：|z|<=0.56 不动；向外按 tuck(x) 拉进。
 *  门/灯带/缝隙框等贴面零件用同一公式 → 永远贴合曲面。 */
function bendZ(g) {
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i);
    const a = Math.abs(z);
    if (a <= HALF_W) continue;
    const t = (a - HALF_W) / (SIDE_W - HALF_W);
    p.setZ(i, Math.sign(z) * (a - tuck(p.getX(i)) * t));
  }
  p.needsUpdate = true;
  return g;
}

/** 自适应平滑法线（非索引输出）。
 *  flatAxis 给定时：法线几乎平行该轴的「端面」保持绝对平整（防大面起鼓），
 *  其余面按角度阈值在同位置邻面间平均（顺带缝合 lathe 接缝）。 */
function smoothNormals(g, angleDeg = 42, flatAxis = null) {
  if (g.index) g = g.toNonIndexed();
  const pos = g.attributes.position;
  const n = pos.count;
  const fn = new Float32Array((n / 3) * 3);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const ab = new THREE.Vector3(), ac = new THREE.Vector3(), nn = new THREE.Vector3();
  for (let t = 0; t < n / 3; t++) {
    a.fromBufferAttribute(pos, t * 3);
    b.fromBufferAttribute(pos, t * 3 + 1);
    c.fromBufferAttribute(pos, t * 3 + 2);
    ab.subVectors(b, a); ac.subVectors(c, a);
    nn.crossVectors(ab, ac);
    if (nn.lengthSq() > 0) nn.normalize();
    fn[t * 3] = nn.x; fn[t * 3 + 1] = nn.y; fn[t * 3 + 2] = nn.z;
  }
  const axisComp = (i) =>
    flatAxis === "x" ? fn[i * 3] : flatAxis === "y" ? fn[i * 3 + 1] : fn[i * 3 + 2];
  const isFlat = (i) => flatAxis !== null && Math.abs(axisComp(i)) > 0.985;

  const groups = new Map();
  const key = (i) =>
    Math.round(pos.getX(i) * 2000) + "," +
    Math.round(pos.getY(i) * 2000) + "," +
    Math.round(pos.getZ(i) * 2000);
  for (let i = 0; i < n; i++) {
    const k = key(i);
    let arr = groups.get(k);
    if (!arr) { arr = []; groups.set(k, arr); }
    arr.push(i);
  }
  const cosT = Math.cos((angleDeg * Math.PI) / 180);
  const out = new Float32Array(n * 3);
  for (const arr of groups.values()) {
    for (const i of arr) {
      const ti = (i / 3) | 0;
      if (isFlat(ti)) {                      // 端面：保持自身面法线，绝不参与平均
        out[i * 3] = fn[ti * 3];
        out[i * 3 + 1] = fn[ti * 3 + 1];
        out[i * 3 + 2] = fn[ti * 3 + 2];
        continue;
      }
      const fx = fn[ti * 3], fy = fn[ti * 3 + 1], fz = fn[ti * 3 + 2];
      let sx = 0, sy = 0, sz = 0;
      for (const j of arr) {
        const tj = (j / 3) | 0;
        if (isFlat(tj)) continue;            // 端面不向相邻面泄漏
        const gx = fn[tj * 3], gy = fn[tj * 3 + 1], gz = fn[tj * 3 + 2];
        if (fx * gx + fy * gy + fz * gz >= cosT) { sx += gx; sy += gy; sz += gz; }
      }
      const l = Math.hypot(sx, sy, sz) || 1;
      out[i * 3] = sx / l; out[i * 3 + 1] = sy / l; out[i * 3 + 2] = sz / l;
    }
  }
  g.setAttribute("normal", new THREE.BufferAttribute(out, 3));
  return g;
}

/** 挤出件统一收尾：弯折/位移之后调用（端面保持平整） */
const finZ = (g) => smoothNormals(g, 42, "z");
const finY = (g) => smoothNormals(g, 42, "y");

function shapeOf(pts) {
  const s = new THREE.Shape();
  s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  s.closePath();
  return s;
}
function holeOf(shape, pts) {
  const h = new THREE.Path();
  h.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) h.lineTo(pts[i][0], pts[i][1]);
  h.closePath();
  shape.holes.push(h);
}

/** 沿 Z 挤出（含 bevel），结果 z ∈ [z0,z1] */
function extrudeZ(shape, z0, z1, bevel = 0.04, bevelSeg = 3) {
  const span = Math.abs(z1 - z0);
  const bt = Math.min(bevel, span * 0.4);
  const depth = span - 2 * bt;
  const g = new THREE.ExtrudeGeometry(shape, {
    depth, bevelEnabled: true, bevelThickness: bt, bevelSize: bevel,
    bevelSegments: bevelSeg, steps: 1,
  });
  g.translate(0, 0, Math.min(z0, z1) + bt);
  return g;
}

/** 沿 Y 挤出（plan 形状 → 竖直），结果 y ∈ [y0,y1] */
function extrudeY(shape, y0, y1, bevel = 0.01) {
  const span = Math.abs(y1 - y0);
  const bt = Math.min(bevel, span * 0.4);
  const depth = span - 2 * bt;
  const g = new THREE.ExtrudeGeometry(shape, {
    depth, bevelEnabled: true, bevelThickness: bt, bevelSize: bevel,
    bevelSegments: 2, steps: 1,
  });
  g.rotateX(-Math.PI / 2);
  g.translate(0, Math.min(y0, y1) + bt, 0);
  return g;
}

/** 轴对齐盒（绝对坐标），硬边 */
function box3(x0, x1, y0, y1, z0, z1) {
  const g = new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0);
  g.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return g;
}
/** 圆角软盒（分段 + 平滑 → 边缘微圆，座椅/电池用） */
function softBox(w, h, d, seg = 3) {
  return smoothNormals(new THREE.BoxGeometry(w, h, d, seg, seg, seg), 135);
}
/** 弯折过的硬盒：重算法线但保持面间硬朗 */
const bentBox = (x0, x1, y0, y1, z0, z1) =>
  smoothNormals(bendZ(box3(x0, x1, y0, y1, z0, z1)), 45);

/** 顶点 y += fn(x)（把平面挤出件贴到倾斜车身表面） */
function shiftY(g, fn) {
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, p.getY(i) + fn(p.getX(i)));
  p.needsUpdate = true;
  return g;
}
/** 座舱罩 tumblehome：向车顶收窄 */
function taperZ(g) {
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const y = p.getY(i);
    const t = Math.min(1, Math.max(0, (y - 0.75) / 0.40));
    p.setZ(i, p.getZ(i) * (1 - 0.18 * t));
  }
  p.needsUpdate = true;
  return g;
}

/** 多边形偏移（+外扩 / -内缩），按绕向决定外法线 */
function offsetPolygon(pts, d) {
  const n = pts.length;
  let area = 0;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % n];
    area += x1 * y2 - x2 * y1;
  }
  const sgn = area > 0 ? 1 : -1;
  const out = [];
  for (let i = 0; i < n; i++) {
    const p = pts[i], a = pts[(i - 1 + n) % n], b = pts[(i + 1) % n];
    let n1x = (p[1] - a[1]) * sgn, n1y = -(p[0] - a[0]) * sgn;
    let n2x = (b[1] - p[1]) * sgn, n2y = -(b[0] - p[0]) * sgn;
    const l1 = Math.hypot(n1x, n1y) || 1, l2 = Math.hypot(n2x, n2y) || 1;
    const nx = n1x / l1 + n2x / l2, ny = n1y / l1 + n2y / l2;
    const l = Math.hypot(nx, ny) || 1;
    out.push([p[0] + (nx / l) * d, p[1] + (ny / l) * d]);
  }
  return out;
}

/** 圆角矩形点列 */
function roundedRect(x0, x1, y0, y1, r) {
  const rect = [[x1, y1], [x0, y1], [x0, y0], [x1, y0]];
  const out = [];
  for (let i = 0; i < 4; i++) {
    const p = rect[i], prev = rect[(i + 3) % 4], next = rect[(i + 1) % 4];
    const d1 = [prev[0] - p[0], prev[1] - p[1]];
    const d2 = [next[0] - p[0], next[1] - p[1]];
    const l1 = Math.hypot(d1[0], d1[1]), l2 = Math.hypot(d2[0], d2[1]);
    const a = [p[0] + (d1[0] / l1) * r, p[1] + (d1[1] / l1) * r];
    const b = [p[0] + (d2[0] / l2) * r, p[1] + (d2[1] / l2) * r];
    for (let t = 0; t <= 5; t++) {
      const k = t / 5, u = 1 - k;
      out.push([
        u * u * a[0] + 2 * u * k * p[0] + k * k * b[0],
        u * u * a[1] + 2 * u * k * p[1] + k * k * b[1],
      ]);
    }
  }
  return out;
}

/** 轮拱圆弧：后唇 → 拱顶 → 前唇（行进 +X） */
function archArc(cx, r = ARCH_R) {
  const dy = LIP_Y - ARCH_Y;
  const dx = Math.sqrt(Math.max(0.0001, r * r - dy * dy));
  const a0 = Math.atan2(dy, -dx);
  const a1 = Math.atan2(dy, dx);
  const pts = [];
  for (let i = 0; i <= 20; i++) {
    const ang = a0 + (a1 - a0) * (i / 20);
    pts.push([cx + r * Math.cos(ang), ARCH_Y + r * Math.sin(ang)]);
  }
  return pts;
}
function archY(x, cx) {
  const d = x - cx;
  if (Math.abs(d) >= ARCH_R) return -Infinity;
  return ARCH_Y + Math.sqrt(ARCH_R * ARCH_R - d * d);
}

function spline(ctrl, n) {
  const curve = new THREE.SplineCurve(ctrl.map(([x, y]) => new THREE.Vector2(x, y)));
  return curve.getPoints(n).map((v) => [v.x, v.y]);
}
/** 在按 x 降序排列的折线上线性查值 */
function lookupY(poly, x) {
  if (x >= poly[0][0]) return poly[0][1];
  const last = poly[poly.length - 1];
  if (x <= last[0]) return last[1];
  for (let i = 1; i < poly.length; i++) {
    const a = poly[i - 1], b = poly[i];
    if (x <= a[0] && x >= b[0]) {
      const t = (a[0] - x) / ((a[0] - b[0]) || 1e-9);
      return a[1] + (b[1] - a[1]) * t;
    }
  }
  return last[1];
}

/* ================================================================
 * 车身轮廓（手写控制点 → 密采样）
 * ================================================================ */

/** 侧板顶缘：低鼻 → 前拱隆起 → cowl 下沉 → 腰线 → 后拱鼓包 → 斜切尾 */
const SIDE_TOP_CTRL = [
  [2.22, 0.455], [2.12, 0.462], [2.00, 0.476], [1.90, 0.505],
  [1.82, 0.552], [1.76, 0.615], [1.70, 0.672], [1.62, 0.732],
  [1.54, 0.776], [1.46, 0.806], [1.38, 0.828], [1.35, 0.840],
  [1.30, 0.836], [1.24, 0.818], [1.18, 0.797], [1.12, 0.777],
  [1.06, 0.752], [1.00, 0.722], [0.94, 0.745], [0.88, 0.766],
  [0.80, 0.790], [0.70, 0.807], [0.60, 0.820], [0.45, 0.834],
  [0.30, 0.846], [0.14, 0.856], [-0.05, 0.864], [-0.25, 0.870],
  [-0.45, 0.875], [-0.65, 0.880], [-0.85, 0.886], [-1.02, 0.895],
  [-1.18, 0.905], [-1.35, 0.910], [-1.50, 0.903], [-1.65, 0.897],
  [-1.76, 0.891], [-1.88, 0.885], [-2.00, 0.878], [-2.12, 0.871],
  [-2.20, 0.873], [-2.25, 0.882],   // Kamm 切尾：腰线保持到尾 + 鸭尾微翘
];
const SIDE_TOP = (() => {
  const dense = spline(SIDE_TOP_CTRL, 480);
  for (const p of dense) {                 // 轮拱安全钳制：顶缘永在拱弧之上
    const lim = Math.max(archY(p[0], 1.35), archY(p[0], -1.35)) + 0.016;
    if (p[1] < lim) p[1] = lim;
  }
  return dense;
})();
const sideTop = (x) => lookupY(SIDE_TOP, x);

/** 中轴 tub 顶缘（机盖段） */
const HOOD = spline([
  [2.21, 0.44], [2.10, 0.452], [1.95, 0.466], [1.80, 0.482],
  [1.65, 0.50], [1.50, 0.518], [1.35, 0.536], [1.22, 0.556],
  [1.10, 0.585], [1.02, 0.628], [0.985, 0.676], [0.965, 0.735],
], 220);
const hoodTop = (x) => lookupY(HOOD, x);

/** 中轴 tub 后甲板顶缘 */
const DECK = spline([
  [-0.96, 0.885], [-1.06, 0.880], [-1.20, 0.876], [-1.35, 0.871],
  [-1.50, 0.866], [-1.65, 0.860], [-1.80, 0.854], [-1.95, 0.847],
  [-2.06, 0.842], [-2.16, 0.838],
], 160);
const deckTop = (x) => lookupY(DECK, x);

/** 中轴 tub 侧影（CCW：底后→前 → 前脸 → 顶前→后 → 座舱缺口 → 甲板 → 尾脸） */
function centerProfile() {
  const pts = [
    [-2.16, 0.33], [-2.02, 0.27], [-1.85, 0.225], [-1.60, 0.19],
    [-1.20, 0.172], [-0.60, 0.162], [0, 0.157], [0.60, 0.162],
    [1.20, 0.172], [1.70, 0.186], [2.02, 0.182], [2.14, 0.176],
    [2.22, 0.19], [2.24, 0.30], [2.24, 0.40],
  ];
  for (const p of HOOD) pts.push(p);
  pts.push(
    [0.93, 0.735], [0.91, 0.62], [0.895, 0.50], [0.88, 0.42],
    [0.855, 0.372], [0.80, 0.362],
    [0.60, 0.357], [0, 0.354], [-0.60, 0.358], [-0.74, 0.372],
    [-0.80, 0.42], [-0.85, 0.52], [-0.89, 0.64], [-0.925, 0.76],
  );
  for (const p of DECK) pts.push(p);
  pts.push([-2.24, 0.834], [-2.24, 0.55], [-2.22, 0.42]);
  return pts;
}

/** 侧板侧影（CCW：底后→前含双拱 → 前脸 → 顶缘前→后 → 尾脸） */
function sideProfile() {
  const pts = [
    [-2.20, 0.30], [-2.10, 0.255], [-1.95, 0.225], [-1.82, 0.205],
  ];
  pts.push(...archArc(-1.35));                // 后拱：后唇 → 顶 → 前唇
  pts.push(
    [-0.90, 0.196], [-0.45, 0.192], [0, 0.190], [0.45, 0.192],
    [0.85, 0.195],
  );
  pts.push(...archArc(1.35));                 // 前拱
  pts.push([1.90, 0.194], [2.06, 0.188], [2.16, 0.182]);
  pts.push([2.23, 0.20], [2.245, 0.32], [2.24, 0.42]);
  for (const p of SIDE_TOP) pts.push(p);
  pts.push([-2.26, 0.64], [-2.25, 0.50], [-2.22, 0.40]);
  return pts;
}

/* ================================================================
 * mesh / 装配工具
 * ================================================================ */
function mesh(geo, mat, part, role, name) {
  const m = new THREE.Mesh(geo, mat);
  m.userData.partName = part;
  m.userData.materialRole = role;
  if (name) m.name = name;
  return m;
}
/** 绝对坐标建好的 mesh 挂到 pivot 组（局部 = 绝对 − pivot）
 *  兼容两种调用：attach(group, [m1, m2]) 与 attach(group, m1, m2, ...) */
function attach(group, ...meshes) {
  const list = meshes.length === 1 && Array.isArray(meshes[0]) ? meshes[0] : meshes;
  const p = group.position;
  for (const m of list) {
    m.position.set(m.position.x - p.x, m.position.y - p.y, m.position.z - p.z);
    group.add(m);
  }
  return group;
}

/* ================================================================
 * 零件构建
 * ================================================================ */

/* ---------- 车轮 ---------- */
function tireProfile() {
  return [
    [0.288, -0.150], [0.322, -0.149], [0.345, -0.144], [0.356, -0.135],
    [0.360, -0.125], [0.360, -0.120],
    [0.360, -0.086], [0.350, -0.084], [0.350, -0.066], [0.360, -0.064],
    [0.360, -0.011], [0.350, -0.009], [0.350, 0.009], [0.360, 0.011],
    [0.360, 0.064], [0.350, 0.066], [0.350, 0.084], [0.360, 0.086],
    [0.360, 0.120], [0.360, 0.125], [0.356, 0.135], [0.345, 0.144],
    [0.322, 0.149], [0.288, 0.150],
  ];
}

/** 轮毂组：局部 XY 平面、轴向 Z、辐面朝 +Z（右侧整体绕 Y 转 180° 朝外） */
function buildRim() {
  const g = new THREE.Group();
  g.name = "rim";
  g.userData.subRole = "rim";
  const m = getRoleMaterials().metal;
  const add = (geo, nm) => {
    const mm = mesh(geo, m, null, null, nm);
    g.add(mm);
    return mm;
  };
  const barrel = new THREE.CylinderGeometry(0.292, 0.292, 0.30, 48, 1, true);
  barrel.rotateX(Math.PI / 2);
  add(barrel, "barrel");
  for (const z of [-0.145, 0.145]) {
    const lip = new THREE.TorusGeometry(0.287, 0.011, 8, 48);
    lip.translate(0, 0, z);
    add(lip, "lip");
  }
  const ring = new THREE.TorusGeometry(0.262, 0.019, 8, 48);
  ring.translate(0, 0, 0.102);
  add(ring, "ring");
  for (let i = 0; i < 5; i++) {               // 5 组双辐（10 辐）
    const base = (i / 5) * Math.PI * 2;
    for (const off of [-0.15, 0.15]) {
      const spoke = new THREE.BoxGeometry(0.196, 0.044, 0.030);
      spoke.translate(0.168, 0, 0.102);
      spoke.rotateZ(base + off);
      add(spoke, "spoke");
    }
  }
  const hub = new THREE.CylinderGeometry(0.072, 0.072, 0.06, 24);
  hub.rotateX(Math.PI / 2); hub.translate(0, 0, 0.095);
  add(hub, "hub");
  const cap = new THREE.CylinderGeometry(0.042, 0.042, 0.068, 20);
  cap.rotateX(Math.PI / 2); cap.translate(0, 0, 0.10);
  add(cap, "cap");
  return g;
}

function buildWheel(name, x, z, side) {
  const mats = getRoleMaterials();
  const g = new THREE.Group();
  g.name = name;
  g.position.set(x, ARCH_Y, z);

  const tg = new THREE.LatheGeometry(
    tireProfile().map(([r, y]) => new THREE.Vector2(r, y)), 64,
  );
  tg.rotateX(Math.PI / 2);                     // 轴 → Z
  const tire = mesh(smoothNormals(tg, 46, "z"), mats.tire, name, "tire", "tire");

  const rim = buildRim();
  rim.traverse((o) => {
    if (o.isMesh) {
      o.userData.partName = name;
      o.userData.materialRole = "metal";
    }
  });
  if (side < 0) rim.rotation.y = Math.PI;      // 右侧辐面朝外

  // 刹车盘：双摩擦片 + 中心盘帽（帽朝车内）
  const discParts = [];
  for (const dz of [-0.014, 0.014]) {
    const pg = new THREE.CylinderGeometry(0.235, 0.235, 0.007, 48);
    pg.rotateX(Math.PI / 2); pg.translate(0, 0, dz);
    discParts.push(mesh(smoothNormals(pg, 60, "z"), mats.metal, name, "metal", "disc"));
  }
  const hat = new THREE.CylinderGeometry(0.126, 0.126, 0.05, 32);
  hat.rotateX(Math.PI / 2); hat.translate(0, 0, -0.024 * side);
  discParts.push(mesh(smoothNormals(hat, 60, "z"), mats.metal, name, "metal", "disc_hat"));

  // 卡钳（独立材质；accessories 换色）—— role 用 "caliper"：
  // 不能标 "paint"，否则 applyRoles 会把它换成共享车漆材质，
  // accessories 再 setHex 就会把全车染成卡钳色
  const calMat = newCaliperMaterial();
  const arc = new THREE.TorusGeometry(0.222, 0.030, 10, 22, 1.35);
  arc.rotateZ(1.594);                          // 弧心 ≈130°（后上位）
  const cal1 = mesh(arc, calMat, name, "caliper", `${name}_caliper`);
  cal1.userData.subRole = "caliper";
  const bridge = new THREE.BoxGeometry(0.075, 0.05, 0.072);
  bridge.rotateZ((130 * Math.PI) / 180);
  bridge.translate(Math.cos((130 * Math.PI) / 180) * 0.222,
                   Math.sin((130 * Math.PI) / 180) * 0.222, 0);
  const cal2 = mesh(bridge, calMat, name, "caliper", `${name}_caliper_bridge`);
  cal2.userData.subRole = "caliper";

  g.add(tire, rim, ...discParts, cal1, cal2);
  return g;
}

/* ---------- 前灯（分层：背板 → blade → 分隔 → lens） ---------- */
function buildFrontLight(side) {
  const mats = getRoleMaterials();
  const part = side > 0 ? "light_front_left" : "light_front_right";
  const g = new THREE.Group();
  g.name = part;
  const za = side > 0 ? 0.57 : -0.94;
  const zb = side > 0 ? 0.94 : -0.57;
  const parts = [];
  parts.push(mesh(bentBox(2.280, 2.289, 0.352, 0.488, za, zb),
    mats.trim, part, "trim", "backing"));
  for (const y of [0.383, 0.415, 0.447]) {
    parts.push(mesh(bentBox(2.289, 2.2935, y, y + 0.015, za + 0.015, zb - 0.015),
      mats.light, part, "light", "blade"));
  }
  parts.push(mesh(bentBox(2.289, 2.294, 0.404, 0.411, za + 0.015, zb - 0.015),
    mats.metal, part, "metal", "divider"));
  parts.push(mesh(bentBox(2.2935, 2.300, 0.346, 0.490, za + 0.006, zb - 0.006),
    mats.glass, part, "glass", "lens"));
  g.position.set(2.10, 0.415, side * 0.755);
  attach(g, parts);
  return g;
}

/* ---------- 尾灯带 ---------- */
function buildRearBar() {
  const mats = getRoleMaterials();
  const part = "light_rear_bar";
  const g = new THREE.Group();
  g.name = part;
  const parts = [];
  // 整体 +0.021x：背板埋进尾面 5mm，消灭悬浮黑腔
  parts.push(mesh(box3(-2.279, -2.235, 0.595, 0.715, -0.50, 0.50),
    mats.trim, part, "trim", "backing"));
  parts.push(mesh(box3(-2.284, -2.2785, 0.622, 0.688, -0.487, 0.487),
    mats.lightRear, part, "light", "blade"));
  for (let i = 0; i < 9; i++) {               // 分段节奏（Evija 式）
    const z = -0.44 + i * 0.11;
    const w = 0.075 - 0.004 * Math.abs(i - 4);
    parts.push(mesh(box3(-2.287, -2.283, 0.630, 0.680, z - w / 2, z + w / 2),
      mats.lightRear, part, "light", `seg_${i}`));
  }
  for (const s of [1, -1]) {                  // 包角（绕到侧板尾脸）
    const za = s > 0 ? 0.57 : -0.86;
    const zb = s > 0 ? 0.86 : -0.57;
    parts.push(mesh(bentBox(-2.291, -2.249, 0.605, 0.705, za, zb),
      mats.lightRear, part, "light", s > 0 ? "wrap_L" : "wrap_R"));
  }
  g.position.set(-2.2, 0.66, 0);
  attach(g, parts);
  return g;
}

/* ---------- 门 ---------- */
/* 门轮廓（x, y）：顶边 = 肩线 S(x) - 0.015（腰线带之下） */
const DOOR_OUTLINE = [
  [0.78, 0.609], [0.72, 0.619], [0.5, 0.653], [0.35, 0.648],
  [0.15, 0.641], [0, 0.647], [-0.2, 0.677], [-0.4, 0.703],
  [-0.56, 0.726],
  [-0.575, 0.55], [-0.585, 0.40], [-0.59, 0.27],
  [-0.4, 0.266], [0, 0.262], [0.4, 0.264], [0.78, 0.27],
];
/** 门上的文丘里浅内陷槽 */
const DOOR_VENT = (() => {
  const top = spline([[0.70, 0.375], [0.40, 0.415], [0.05, 0.45],
                      [-0.30, 0.475], [-0.56, 0.495]], 30);
  const bot = spline([[0.70, 0.295], [0.40, 0.325], [0.05, 0.355],
                      [-0.30, 0.38], [-0.56, 0.395]], 30);
  return [...top, ...bot.reverse()];
})();

function buildDoor(side) {
  const mats = getRoleMaterials();
  const left = side > 0;
  const part = left ? "door_left" : "door_right";
  const g = new THREE.Group();
  g.name = part;

  // 侧别 z 区间（左 +z / 右 −z；bendZ 按 |z| 对称，无需翻面）
  const za = side > 0 ? [0.992, 1.012] : [-1.012, -0.992];
  const zi = side > 0 ? [0.9855, 0.991] : [-0.991, -0.9855];
  const zh = side > 0 ? [1.008, 1.019] : [-1.019, -1.008];

  // 外皮肤（带内陷槽开孔）
  const skinShape = shapeOf(DOOR_OUTLINE);
  holeOf(skinShape, DOOR_VENT);
  const skinGeo = bendZ(extrudeZ(skinShape, za[0], za[1], 0.004));
  const skin = mesh(finZ(skinGeo), mats.paint, part, "paint", "skin");

  // 内衬板（垫住内陷槽；开门时呈深色内面）
  const innerGeo = bendZ(extrudeZ(shapeOf(DOOR_OUTLINE), zi[0], zi[1], 0.0025));
  const inner = mesh(finZ(innerGeo), mats.trim, part, "trim", "inner");

  // 拉手
  const handle = mesh(bentBox(-0.52, -0.42, 0.585, 0.615, zh[0], zh[1]),
    mats.trim, part, "trim", "handle");

  g.position.set(0.05, 0.80, side * 0.88);
  attach(g, [skin, inner, handle]);
  return g;
}

/* ---------- 尾翼 ---------- */
function buildWing() {
  const mats = getRoleMaterials();
  const g = new THREE.Group();
  g.name = "wing_rear";
  // 翼型剖面（弦向 X、厚度 Y）→ 沿 Z 挤出
  const foil = [
    [0.22, 0.0], [0.205, 0.020], [0.14, 0.034], [0.02, 0.040],
    [-0.12, 0.036], [-0.22, 0.024], [-0.235, 0.008], [-0.235, 0.0],
    [-0.22, -0.006], [-0.10, -0.014], [0.05, -0.018], [0.16, -0.012],
    [0.215, -0.005],
  ];
  const wingGeo = extrudeZ(shapeOf(foil), -0.90, 0.90, 0.012, 2);
  finZ(wingGeo);
  const wing = mesh(wingGeo, mats.paint, "wing_rear", "paint", "plane");
  wing.position.set(-2.0, 0.97, 0);
  wing.rotation.z = 0.105;                    // 攻角
  const parts = [wing];
  // 端板：切角轮廓（前上角斜切），不再是方盒子
  const epShape = shapeOf([
    [-1.915, 0.925], [-2.085, 0.925], [-2.085, 1.040],
    [-2.025, 1.075], [-1.915, 1.075],
  ]);
  for (const s of [1, -1]) {
    const epGeo = s > 0 ? extrudeZ(epShape, 0.897, 0.913, 0.006, 2)
                        : extrudeZ(epShape, -0.913, -0.897, 0.006, 2);
    const m = mesh(finZ(epGeo), mats.paint, "wing_rear", "paint",
      s > 0 ? "endplate_L" : "endplate_R");
    parts.push(m);
  }
  for (const s of [1, -1]) {                  // 鹅颈支臂
    const st = new THREE.BoxGeometry(0.045, 0.115, 0.05);
    const m = mesh(st, mats.paint, "wing_rear", "paint",
      s > 0 ? "strut_L" : "strut_R");
    m.position.set(-1.98, 0.902, s * 0.52);
    parts.push(m);
  }
  g.position.set(-2.0, 0.97, 0);
  attach(g, parts);
  return g;
}

/* ---------- 扩散器 ---------- */
function buildDiffuser() {
  const mats = getRoleMaterials();
  const g = new THREE.Group();
  g.name = "diffuser_rear";
  const rot = -0.262;
  const parts = [];
  const ramp = new THREE.BoxGeometry(0.52, 0.03, 1.16);
  ramp.rotateZ(rot);
  const rm = mesh(ramp, mats.trim, "diffuser_rear", "trim", "ramp");
  rm.position.set(-1.98, 0.235, 0);
  parts.push(rm);
  for (const z of [-0.5, -0.25, 0, 0.25, 0.5]) {   // 纵向鳍片
    const fin = new THREE.BoxGeometry(0.48, 0.10, 0.016);
    fin.rotateZ(rot);
    const m = mesh(fin, mats.trim, "diffuser_rear", "trim", "fin");
    m.position.set(-1.98, 0.29, z);
    parts.push(m);
  }
  for (const s of [1, -1]) {                  // 侧板
    const sp = new THREE.BoxGeometry(0.5, 0.13, 0.02);
    sp.rotateZ(rot);
    const m = mesh(sp, mats.trim, "diffuser_rear", "trim", "sideplate");
    m.position.set(-1.98, 0.28, s * 0.585);
    parts.push(m);
  }
  const tail = new THREE.BoxGeometry(0.30, 0.15, 1.14);
  const tm = mesh(tail, mats.trim, "diffuser_rear", "trim", "tail_block");
  tm.position.set(-2.13, 0.335, 0);
  parts.push(tm);
  g.position.set(-1.98, 0.24, 0);
  attach(g, parts);
  return g;
}

/* ---------- 座椅 ---------- */
function buildSeat(name, sx, sz) {
  const mats = getRoleMaterials();
  const g = new THREE.Group();
  g.name = name;
  const parts = [];
  // 以座舱内（车体坐标 sx,0.40,sz）为原点的局部几何
  const add = (geo, role, nm, px, py, pz, rz = 0) => {
    const m = mesh(geo, role === "metal" ? mats.metal : mats.carbon,
      name, role, nm);
    m.position.set(px, py, pz);
    m.rotation.z = rz;
    parts.push(m);
    return m;
  };
  add(softBox(0.40, 0.03, 0.05), "metal", "rail_L", 0, 0.017, -0.13);
  add(softBox(0.40, 0.03, 0.05), "metal", "rail_R", 0, 0.017, 0.13);
  add(softBox(0.44, 0.09, 0.42), "carbon", "cushion", 0, 0.075, 0);
  add(softBox(0.42, 0.07, 0.07), "carbon", "bolster_L",
    -0.01, 0.125, -0.175, 0.15);
  add(softBox(0.42, 0.07, 0.07), "carbon", "bolster_R",
    -0.01, 0.125, 0.175, 0.15);
  add(softBox(0.085, 0.52, 0.40), "carbon", "backrest", -0.24, 0.31, 0, 0.20);
  add(softBox(0.07, 0.36, 0.11), "carbon", "back_bolster_L",
    -0.205, 0.30, -0.155, 0.20);
  add(softBox(0.07, 0.36, 0.11), "carbon", "back_bolster_R",
    -0.205, 0.30, 0.155, 0.20);
  add(softBox(0.10, 0.15, 0.24), "carbon", "headrest",
    -0.325, 0.585, 0, 0.20);
  g.position.set(sx, 0.40, sz);
  attach(g, parts);
  return g;
}

/* ---------- 电池组 ---------- */
function buildBattery() {
  const mats = getRoleMaterials();
  const g = new THREE.Group();
  g.name = "battery_pack";
  const parts = [];
  const caseM = mesh(softBox(1.95, 0.17, 1.02, 2), mats.metal,
    "battery_pack", "metal", "case");
  caseM.position.set(0, 0, 0);
  parts.push(caseM);
  for (const x of [-0.7, -0.35, 0, 0.35, 0.7]) {
    parts.push(mesh(box3(x - 0.02, x + 0.02, 0.075, 0.092, -0.48, 0.48),
      mats.trim, "battery_pack", "trim", "rib"));
  }
  parts.push(mesh(box3(-0.15, 0.15, 0.08, 0.10, -0.10, 0.10),
    mats.light, "battery_pack", "light", "hv_status"));
  g.position.set(0, 0.26, 0);
  attach(g, parts);
  return g;
}

/* ---------- 侧文丘里风道（侧板开孔 + 沉底背板） ---------- */
function venturiSlot() {
  const top = spline([[0.60, 0.36], [0.30, 0.47], [-0.20, 0.545],
                      [-0.70, 0.60], [-1.06, 0.63]], 34);
  const bot = spline([[0.58, 0.265], [0.28, 0.335], [-0.25, 0.40],
                      [-0.78, 0.455], [-1.08, 0.49]], 34);
  return [...top, ...bot.reverse()];
}
function rearVentSlot() {
  const top = spline([[-0.67, 0.52], [-0.75, 0.545],
                      [-0.84, 0.565], [-0.92, 0.585]], 14);
  const bot = spline([[-0.67, 0.42], [-0.75, 0.445],
                      [-0.84, 0.465], [-0.92, 0.485]], 14);
  return [...top, ...bot.reverse()];
}

/* ================================================================
 * 总装
 * ================================================================ */
export function buildCar() {
  const mats = getRoleMaterials();
  const carRoot = new THREE.Group();
  carRoot.name = "car";
  carRoot.userData.dimensions = { length: 4.5, width: 2.0, height: 1.15 };

  const registry = new Map();
  const reg = (name, group, materialRole, explode) => {
    group.userData.partName = name;
    group.userData.materialRole = materialRole;
    registry.set(name, { name, group, materialRole, explode });
    carRoot.add(group);
  };

  /* ---------------- shell（静态结构） ---------------- */
  const shell = new THREE.Group();
  shell.name = "shell";

  // 中轴 tub
  const tubGeo = smoothNormals(extrudeZ(shapeOf(centerProfile()), -0.56, 0.56, 0.04), 42);
  shell.add(mesh(tubGeo, mats.paint, "shell", "paint", "tub_center"));

  // 左右侧板（开文丘里孔 + 门后风道孔）
  const sideShapeBase = sideProfile();
  for (const s of [1, -1]) {
    const sh = shapeOf(sideShapeBase);
    holeOf(sh, venturiSlot());
    holeOf(sh, rearVentSlot());
    const z0 = s > 0 ? 0.56 : -1.0;
    const z1 = s > 0 ? 1.0 : -0.56;
    const geo = bendZ(extrudeZ(sh, z0, z1, 0.045));
    shell.add(mesh(smoothNormals(geo, 42), mats.paint, "shell", "paint",
      s > 0 ? "side_right" : "side_left"));

    // 文丘里沉底背板（比开孔略大 → 边缘掖进面板背后，不留穿帮缝）
    const backGeo = bendZ(extrudeZ(shapeOf(offsetPolygon(venturiSlot(), 0.035)),
      s > 0 ? 0.855 : -0.885, s > 0 ? 0.885 : -0.855, 0.006));
    shell.add(mesh(backGeo, mats.trim, "shell", "trim",
      s > 0 ? "venturi_back_R" : "venturi_back_L"));
    const back2 = bendZ(extrudeZ(shapeOf(offsetPolygon(rearVentSlot(), 0.03)),
      s > 0 ? 0.855 : -0.885, s > 0 ? 0.885 : -0.855, 0.006));
    shell.add(mesh(back2, mats.trim, "shell", "trim",
      s > 0 ? "vent_back_R" : "vent_back_L"));

    // 轮拱：内衬板（遮穿帮）+ 拱顶暗槽
    for (const cx of [1.35, -1.35]) {
      const dx = Math.sqrt(ARCH_R * ARCH_R - (LIP_Y - ARCH_Y) ** 2);
      const arcPts = archArc(cx);
      const platePts = [[cx - dx, LIP_Y], ...arcPts, [cx + dx, LIP_Y]];
      const pz0 = s > 0 ? 0.595 : -0.625;
      const pz1 = s > 0 ? 0.625 : -0.595;
      const plate = bendZ(extrudeZ(shapeOf(platePts), pz0, pz1, 0.008));
      shell.add(mesh(smoothNormals(plate, 42), mats.trim, "shell", "trim",
        `well_plate_${cx > 0 ? "F" : "R"}_${s > 0 ? "L" : "R"}`));

      const tube = new THREE.CylinderGeometry(0.39, 0.39, 0.33, 40, 1, true,
        Math.PI / 2, Math.PI);
      tube.rotateX(Math.PI / 2);
      const tm = mesh(bendZ(smoothNormals(tube, 55)), mats.trim, "shell", "trim",
        `well_liner_${cx > 0 ? "F" : "R"}_${s > 0 ? "L" : "R"}`);
      tm.position.set(cx, ARCH_Y, s * 0.7875);
      shell.add(tm);
    }
  }

  // 地板（封住轮拱平视穿帮 + 平整底盘）
  shell.add(mesh(box3(-2.0, 2.0, 0.095, 0.158, -0.555, 0.555),
    mats.carbon, "shell", "carbon", "undertray"));

  // 前唇（plan 挤出，跟随车头收腰轮廓）
  const splitterShape = shapeOf([
    [1.96, 0.915], [2.14, 0.888], [2.27, 0.845], [2.33, 0.74],
    [2.33, -0.74], [2.27, -0.845], [2.14, -0.888], [1.96, -0.915],
    [1.94, -0.86], [2.08, -0.83], [2.20, -0.79], [2.24, -0.70],
    [2.24, 0.70], [2.20, 0.79], [2.08, 0.83], [1.94, 0.86],
  ]);
  shell.add(mesh(smoothNormals(extrudeY(splitterShape, 0.098, 0.148, 0.012), 42),
    mats.carbon, "shell", "carbon", "splitter"));

  // 前脸进气口（无格栅，仅两角暗口）
  for (const s of [1, -1]) {
    shell.add(mesh(box3(2.26, 2.30, 0.235, 0.315, s > 0 ? 0.18 : -0.46, s > 0 ? 0.46 : -0.18),
      mats.trim, "shell", "trim", s > 0 ? "intake_R" : "intake_L"));
  }
  // 前后保险杠接缝（侧面上的细深线）
  for (const s of [1, -1]) {
    const fz = s > 0 ? [0.975, 1.008] : [-1.008, -0.975];
    shell.add(mesh(bendZ(box3(1.963, 1.977, 0.22, 0.46, fz[0], fz[1])),
      mats.trim, "shell", "trim", `seam_front_${s > 0 ? "L" : "R"}`));
    const rz = s > 0 ? [0.968, 1.0] : [-1.0, -0.968];
    shell.add(mesh(bendZ(box3(-1.977, -1.963, 0.25, 0.78, rz[0], rz[1])),
      mats.trim, "shell", "trim", `seam_rear_${s > 0 ? "L" : "R"}`));
  }
  // 尾部暗口
  for (const s of [1, -1]) {
    shell.add(mesh(box3(-2.30, -2.26, 0.44, 0.56, s > 0 ? 0.24 : -0.48, s > 0 ? 0.48 : -0.24),
      mats.trim, "shell", "trim", `rear_vent_${s > 0 ? "L" : "R"}`));
  }

  // 后甲板散热百叶
  for (let i = 0; i < 6; i++) {
    const x = -1.24 - i * 0.068;
    shell.add(mesh(box3(x - 0.024, x + 0.024, deckTop(x) + 0.042, deckTop(x) + 0.058, -0.46, 0.46),
      mats.trim, "shell", "trim", `deck_slat_${i}`));
  }

  // 相机式后视镜（Theory 1 摄像头 pod）
  for (const s of [1, -1]) {
    const stalk = mesh(bendZ(box3(0.86, 0.93, 0.712, 0.732,
      s > 0 ? 0.945 : -0.975, s > 0 ? 0.975 : -0.945)),
      mats.trim, "shell", "trim", `mirror_stalk_${s > 0 ? "L" : "R"}`);
    const pod = mesh(bendZ(box3(0.84, 0.95, 0.722, 0.762,
      s > 0 ? 0.975 : -1.035, s > 0 ? 1.035 : -0.975)),
      mats.trim, "shell", "trim", `mirror_pod_${s > 0 ? "L" : "R"}`);
    const lens = mesh(bendZ(box3(0.93, 0.952, 0.728, 0.756,
      s > 0 ? 0.985 : -1.03, s > 0 ? 1.03 : -0.985)),
      mats.metal, "shell", "metal", `mirror_lens_${s > 0 ? "L" : "R"}`);
    shell.add(stalk, pod, lens);
  }

  // 座舱内衬：地板 / 侧壁 / 仪表台 / 屏幕 / 方向盘
  shell.add(mesh(box3(-0.72, 0.78, 0.388, 0.412, -0.558, 0.558),
    mats.trim, "shell", "trim", "cabin_floor"));
  for (const s of [1, -1]) {
    shell.add(mesh(box3(-0.70, 0.76, 0.45, 0.70, s > 0 ? 0.538 : -0.558, s > 0 ? 0.558 : -0.538),
      mats.trim, "shell", "trim", `door_card_${s > 0 ? "L" : "R"}`));
  }
  shell.add(mesh(box3(0.855, 0.915, 0.53, 0.67, -0.5, 0.5),
    mats.trim, "shell", "trim", "dash"));
  shell.add(mesh(box3(0.844, 0.856, 0.556, 0.646, -0.18, 0.18),
    mats.light, "shell", "light", "dash_screen"));
  // 方向盘（中置驾驶位）
  {
    const sw = new THREE.Group();
    sw.position.set(0.62, 0.585, 0);
    sw.rotation.z = -0.23;
    const swi = new THREE.Group();
    swi.rotation.y = Math.PI / 2;
    const swRim = mesh(smoothNormals(new THREE.TorusGeometry(0.148, 0.021, 10, 36), 60),
      mats.trim, "shell", "trim", "steering_rim");
    const hub = mesh((() => {
      const c = new THREE.CylinderGeometry(0.048, 0.048, 0.045, 20);
      c.rotateX(Math.PI / 2); return smoothNormals(c, 60);
    })(), mats.metal, "shell", "metal", "steering_hub");
    swi.add(swRim, hub);
    for (const a of [Math.PI / 6, (5 * Math.PI) / 6, (3 * Math.PI) / 2]) {
      const sp = new THREE.BoxGeometry(0.10, 0.026, 0.02);
      sp.translate(0.095, 0, 0.008);
      sp.rotateZ(a);
      swi.add(mesh(sp, mats.trim, "shell", "trim", "steering_spoke"));
    }
    sw.add(swi);
    shell.add(sw);
  }

  // 门缝框 / 机盖缝框（留在车身上，开门开盖后仍可见）
  for (const s of [1, -1]) {
    const frameGeo = extrudeZ(shapeOf(offsetPolygon(DOOR_OUTLINE, 0.014)),
      s > 0 ? 0.994 : -1.008, s > 0 ? 1.008 : -0.994, 0.003);
    bendZ(frameGeo);
    shell.add(mesh(frameGeo, mats.trim, "shell", "trim",
      s > 0 ? "door_gap_R" : "door_gap_L"));
  }
  {
    const rect = [[2.16, 0.44], [1.02, 0.44], [1.02, -0.44], [2.16, -0.44]];
    const R = 0.09;
    const rounded = [];
    for (let i = 0; i < 4; i++) {
      const p = rect[i], prev = rect[(i + 3) % 4], next = rect[(i + 1) % 4];
      const d1 = [prev[0] - p[0], prev[1] - p[1]];
      const d2 = [next[0] - p[0], next[1] - p[1]];
      const l1 = Math.hypot(...d1), l2 = Math.hypot(...d2);
      const a = [p[0] + (d1[0] / l1) * R, p[1] + (d1[1] / l1) * R];
      const b = [p[0] + (d2[0] / l2) * R, p[1] + (d2[1] / l2) * R];
      for (let t = 0; t <= 4; t++) {
        const k = t / 4, u = 1 - k;
        rounded.push([
          u * u * a[0] + 2 * u * k * p[0] + k * k * b[0],
          u * u * a[1] + 2 * u * k * p[1] + k * k * b[1],
        ]);
      }
    }
    const frame = extrudeY(shapeOf(offsetPolygon(rounded, 0.014)), 0.038, 0.048, 0.003);
    shiftY(frame, (x) => hoodTop(x) + 0.040);
    shell.add(mesh(smoothNormals(frame, 42), mats.trim, "shell", "trim", "hood_gap"));
  }

  reg("shell", shell, "paint", { static: true });

  /* ---------------- hood_front ---------------- */
  {
    const g = new THREE.Group();
    g.name = "hood_front";
    const rect = [[2.16, 0.44], [1.02, 0.44], [1.02, -0.44], [2.16, -0.44]];
    const R = 0.09;
    const rounded = [];
    for (let i = 0; i < 4; i++) {
      const p = rect[i], prev = rect[(i + 3) % 4], next = rect[(i + 1) % 4];
      const d1 = [prev[0] - p[0], prev[1] - p[1]];
      const d2 = [next[0] - p[0], next[1] - p[1]];
      const l1 = Math.hypot(...d1), l2 = Math.hypot(...d2);
      const a = [p[0] + (d1[0] / l1) * R, p[1] + (d1[1] / l1) * R];
      const b = [p[0] + (d2[0] / l2) * R, p[1] + (d2[1] / l2) * R];
      for (let t = 0; t <= 4; t++) {
        const k = t / 4, u = 1 - k;
        rounded.push([
          u * u * a[0] + 2 * u * k * p[0] + k * k * b[0],
          u * u * a[1] + 2 * u * k * p[1] + k * k * b[1],
        ]);
      }
    }
    const panel = extrudeY(shapeOf(rounded), 0.0, 0.016, 0.004);
    shiftY(panel, (x) => hoodTop(x) + 0.043);
    const pm = mesh(smoothNormals(panel, 42), mats.paint, "hood_front", "paint", "panel");
    g.position.set(1.0, 0.686, 0);
    attach(g, pm);
    reg("hood_front", g, "paint", { type: "hinge_up" });
  }

  /* ---------------- 门 ---------------- */
  reg("door_left", buildDoor(1), "paint", { type: "gullwing" });
  reg("door_right", buildDoor(-1), "paint", { type: "gullwing" });

  /* ---------------- 座舱罩 ---------------- */
  {
    const g = new THREE.Group();
    g.name = "canopy";
    const frontBot = [0.96, sideTop(0.96) - 0.015];
    const rearBot = [-1.24, sideTop(-1.24) - 0.015];
    const outerCtrl = [
      frontBot, [0.88, 0.83], [0.72, 0.95], [0.55, 1.055],
      [0.38, 1.115], [0.20, 1.127], [0.0, 1.127], [-0.25, 1.123],
      [-0.50, 1.105], [-0.72, 1.065], [-0.92, 1.005], [-1.08, 0.945],
      [-1.18, 0.905], rearBot,
    ];
    const outer = spline(outerCtrl, 140);
    // 底边：沿侧顶缘 −0.015（后 → 前）
    const bottom = [];
    for (let x = -1.24; x <= 0.961; x += 0.03) bottom.push([x, sideTop(x) - 0.015]);
    bottom.push([0.96, sideTop(0.96) - 0.015]);
    const outline = [...outer, ...bottom.reverse()];

    const inner = offsetPolygon(outline, -0.055);
    const shellShape = shapeOf(outline);
    holeOf(shellShape, inner);
    const shellGeo = taperZ(extrudeZ(shellShape, -0.92, 0.92, 0.025, 3));
    const shellM = mesh(smoothNormals(shellGeo, 42), mats.glass, "canopy", "glass", "glass_shell");

    const panes = [];
    const paneShape = shapeOf(offsetPolygon(inner, -0.006));
    for (const s of [1, -1]) {
      const z0 = s > 0 ? 0.885 : -0.903;
      const z1 = s > 0 ? 0.903 : -0.885;
      const pg = taperZ(extrudeZ(paneShape, z0, z1, 0.004, 2));
      panes.push(mesh(smoothNormals(pg, 42), mats.glass, "canopy", "glass",
        s > 0 ? "pane_L" : "pane_R"));
    }
    // 框饰条（贴着外轮廓 0.035 宽，压在玻璃框面上）
    const framePoly = [...outline, ...offsetPolygon(outline, -0.035).reverse()];
    const frames = [];
    for (const s of [1, -1]) {
      const z0 = s > 0 ? 0.905 : -0.935;
      const z1 = s > 0 ? 0.935 : -0.905;
      const fg = taperZ(extrudeZ(shapeOf(framePoly), z0, z1, 0.004, 2));
      frames.push(mesh(smoothNormals(fg, 42), mats.trim, "canopy", "trim",
        s > 0 ? "frame_L" : "frame_R"));
    }
    g.position.set(-0.94, 0.87, 0);
    attach(g, shellM, ...panes, ...frames);
    reg("canopy", g, "glass", { type: "lift_tilt" });
  }

  /* ---------------- technology band 腰线 ---------------- */
  for (const s of [1, -1]) {
    const g = new THREE.Group();
    g.name = s > 0 ? "band_left" : "band_right";
    const top = [], bot = [];
    for (let x = 0.90; x >= -1.951; x -= 0.035) {
      top.push([x, sideTop(x) - 0.063]);
      bot.push([x, sideTop(x) - 0.105]);
    }
    const strip = [...top, ...bot.reverse()];
    const z0 = s > 0 ? 0.994 : -1.010;
    const z1 = s > 0 ? 1.010 : -0.994;
    const geo = bendZ(extrudeZ(shapeOf(strip), z0, z1, 0.003, 2));
    const m = mesh(smoothNormals(geo, 42), mats.trim,
      s > 0 ? "band_left" : "band_right", "trim", "strip");
    g.position.set(-0.15, sideTop(-0.15) - 0.084, s * 0.90);
    attach(g, m);
    reg(s > 0 ? "band_left" : "band_right", g, "trim", { type: "slide_lateral" });
  }

  /* ---------------- 尾翼 / 扩散器 ---------------- */
  reg("wing_rear", buildWing(), "paint", { type: "lift_back" });
  reg("diffuser_rear", buildDiffuser(), "trim", { type: "slide_back" });

  /* ---------------- 车轮 ---------------- */
  reg("wheel_FL", buildWheel("wheel_FL", 1.35, 0.80, 1), "tire", { type: "spin_out" });
  reg("wheel_FR", buildWheel("wheel_FR", 1.35, -0.80, -1), "tire", { type: "spin_out" });
  reg("wheel_RL", buildWheel("wheel_RL", -1.35, 0.80, 1), "tire", { type: "spin_out" });
  reg("wheel_RR", buildWheel("wheel_RR", -1.35, -0.80, -1), "tire", { type: "spin_out" });

  /* ---------------- 电池 / 座椅 ---------------- */
  reg("battery_pack", buildBattery(), "metal", { type: "drop_down" });
  reg("seat_center", buildSeat("seat_center", 0.16, 0), "carbon", { type: "rail_up" });
  reg("seat_left", buildSeat("seat_left", -0.45, 0.27), "carbon", { type: "rail_up" });
  reg("seat_right", buildSeat("seat_right", -0.45, -0.27), "carbon", { type: "rail_up" });

  /* ---------------- 灯组 ---------------- */
  reg("light_front_left", buildFrontLight(1), "light", { type: "slide_forward" });
  reg("light_front_right", buildFrontLight(-1), "light", { type: "slide_forward" });
  reg("light_rear_bar", buildRearBar(), "light", { type: "slide_back" });

  return { carRoot, registry };
}
