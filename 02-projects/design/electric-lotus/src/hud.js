// src/hud.js —— 全屏 Canvas2D HUD（引线标签 / 选中高亮 / 功率表）
//
// 全部程序化绘制（无图片资源），画在 #hud-canvas 上（pointer-events:none 覆盖层）。
// - 拆解态: 每个零件（shell 除外）一条贝塞尔引线 → 屏幕近侧的标签卡
//   （mono 大写 EN 名 + 中文 · 规格短句 + 细琥珀色刻度），按索引错峰淡入，装回时淡出。
// - 选中态: 投影中心琥珀高亮环 + 加粗标签（未拆解时也显示）。
// - 左下功率表: 圆弧仪表，平时呼吸微动，拆解后拉满（SYS/OPEN）。
// - 缺少 #hud-canvas 时安全 no-op；Node 下（无 document）同样 no-op。

import * as THREE from "three";
import { on, off } from "./events.js";

/** 零件中文名 + 规格短句（panel.js 的拾取读出也复用此表） */
export const PART_LABELS = {
  shell: { cn: "车身壳体", spec: "碳纤维单体壳" },
  hood_front: { cn: "前盖", spec: "轻量开启机盖" },
  door_left: { cn: "左翼门", spec: "鸥翼铰链" },
  door_right: { cn: "右翼门", spec: "鸥翼铰链" },
  canopy: { cn: "座舱罩", spec: "升降式玻璃舱" },
  band_left: { cn: "技术腰线", spec: "左侧光带" },
  band_right: { cn: "技术腰线", spec: "右侧光带" },
  wing_rear: { cn: "尾翼", spec: "主动式尾翼" },
  diffuser_rear: { cn: "扩散器", spec: "底部气动扩散" },
  wheel_FL: { cn: "前左轮", spec: "20寸锻造" },
  wheel_FR: { cn: "前右轮", spec: "20寸锻造" },
  wheel_RL: { cn: "后左轮", spec: "20寸锻造" },
  wheel_RR: { cn: "后右轮", spec: "20寸锻造" },
  battery_pack: { cn: "电池组", spec: "底盘一体化电池" },
  seat_center: { cn: "中置驾驶席", spec: "桶形赛车座椅" },
  seat_left: { cn: "左席", spec: "轻量运动座椅" },
  seat_right: { cn: "右席", spec: "轻量运动座椅" },
  light_front_left: { cn: "前灯左", spec: "矩阵 LED" },
  light_front_right: { cn: "前灯右", spec: "矩阵 LED" },
  light_rear_bar: { cn: "尾灯带", spec: "贯穿式尾灯" },
};

const AMBER = "255, 179, 64";
const ICE = "150, 205, 255";
const TEXT_DIM = "150, 160, 176";
const CARD_W = 178;
const CARD_H = 34;

const MONO = '600 11px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
const MONO_BOLD = '700 11px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
const SANS = '11px system-ui, "Segoe UI", sans-serif';
const TINY = '9px ui-monospace, Menlo, Consolas, monospace';

export function initHud({ camera, renderer, registry, getExploder } = {}) {
  const hasDoc = typeof document !== "undefined";
  const canvas = hasDoc ? document.getElementById("hud-canvas") : null;
  const ctx = canvas && typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;

  // ---- 缺画布 / 缺相机 → 全 no-op（安全降级） ----
  if (!ctx || !camera) {
    return {
      update() {},
      setSelected() {},
      setExploded() {},
      dispose() {},
    };
  }

  const labels = registry instanceof Map ? registry : new Map();

  let W = 0, H = 0, dpr = 1;
  let t = 0;
  let selected = null;
  let exploded = false;
  let explodeT0 = -1e9;
  let labelAlpha = 0;
  let gauge = 0.5;
  let disposed = false;

  // 临时对象
  const _wp = new THREE.Vector3();
  const _dir = new THREE.Vector3();
  const _to = new THREE.Vector3();

  // ---- 事件（模块自接线，集成无需额外挂接） ----
  const unsubs = [
    on("explode:start", () => setExploded(true)),
    on("assemble:start", () => setExploded(false)),
    on("part:pick", (payload) => {
      const name = payload && typeof payload === "object" ? payload.name : payload;
      setSelected(name || null);
    }),
  ];

  function onResize() { resize(true); }

  if (typeof window !== "undefined") {
    window.addEventListener("resize", onResize);
  }

  // ---- 尺寸（DPR + 自适应；每帧检测 client 尺寸变化） ----
  function resize(force) {
    const dprRaw = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    const nextDpr = Math.min(dprRaw, 2);
    const cw = canvas.clientWidth || (typeof window !== "undefined" ? window.innerWidth : 0);
    const ch = canvas.clientHeight || (typeof window !== "undefined" ? window.innerHeight : 0);
    if (!cw || !ch) return;
    if (!force && cw === W && ch === H && nextDpr === dpr) return;
    W = cw; H = ch; dpr = nextDpr;
    canvas.width = Math.max(1, Math.round(W * dpr));
    canvas.height = Math.max(1, Math.round(H * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // ---- 标签卡圆角路径（闭包 ctx） ----
  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ---- 投影：世界坐标 → 屏幕像素；返回 null（在相机背后 / 不可见） ----
  function project(worldPos) {
    camera.getWorldDirection(_dir);
    _to.copy(worldPos).sub(camera.position);
    if (_to.dot(_dir) <= 0.05) return null;
    _wp.copy(worldPos).project(camera);
    if (_wp.z > 1 || _wp.z < -1) return null;
    return {
      x: (_wp.x * 0.5 + 0.5) * W,
      y: (-_wp.y * 0.5 + 0.5) * H,
    };
  }

  function partWorldPos(info) {
    info.group.getWorldPosition(_wp); // 内部会刷新世界矩阵
    return _wp.clone();
  }

  // ---- 引线标签（拆解态） ----
  function drawLabels() {
    if (labelAlpha <= 0.01) return;

    const entries = [];
    for (const [name, info] of labels) {
      if (name === "shell" || !info || !info.group) continue;
      const p = project(partWorldPos(info));
      if (!p) continue;
      if (p.x < -CARD_W || p.x > W + CARD_W || p.y < -CARD_H || p.y > H + CARD_H) continue;
      entries.push({ name, x: p.x, y: p.y, side: p.x < W / 2 ? "left" : "right" });
    }
    if (!entries.length) return;

    // 按侧分列，按投影 Y 排序后均分槽位 → 确定性防重叠
    const slots = [];
    for (const side of ["left", "right"]) {
      const list = entries.filter((e) => e.side === side).sort((a, b) => a.y - b.y);
      const n = list.length;
      if (!n) continue;
      const top = 64;
      const bottom = H - 104;
      list.forEach((e, i) => {
        e.lx = side === "left" ? 20 : W - 20 - CARD_W;
        e.ly = top + ((i + 0.5) * (bottom - top)) / n;
        e.slot = i;
        slots.push(e);
      });
    }

    ctx.textBaseline = "middle";
    for (const e of slots) {
      const meta = PART_LABELS[e.name] || { cn: e.name, spec: "" };
      // 错峰淡入（按列内索引），全局 labelAlpha 控制淡出
      const local = clamp01((t - explodeT0 - e.slot * 0.06) / 0.3);
      const a = labelAlpha * easeOutCubic(local);
      if (a <= 0.02) continue;

      const isSel = selected === e.name;
      const cardX = e.lx;
      const cardY = e.ly;
      const anchorX = e.side === "left" ? cardX + CARD_W : cardX;
      const anchorY = cardY + CARD_H / 2;

      // 零件点 + 贝塞尔引线
      ctx.lineWidth = 1;
      ctx.strokeStyle = `rgba(${AMBER}, ${(isSel ? 0.85 : 0.5) * a})`;
      ctx.beginPath();
      ctx.moveTo(e.x, e.y);
      const c1x = e.x + (anchorX - e.x) * 0.55;
      ctx.bezierCurveTo(c1x, e.y, anchorX, e.y + (anchorY - e.y) * 0.35, anchorX, anchorY);
      ctx.stroke();

      ctx.fillStyle = `rgba(${AMBER}, ${0.95 * a})`;
      ctx.beginPath();
      ctx.arc(e.x, e.y, isSel ? 3.4 : 2.4, 0, Math.PI * 2);
      ctx.fill();

      // 标签卡
      ctx.fillStyle = `rgba(8, 10, 14, ${0.78 * a})`;
      roundRect(cardX, cardY, CARD_W, CARD_H, 4);
      ctx.fill();
      ctx.strokeStyle = `rgba(${AMBER}, ${(isSel ? 0.7 : 0.3) * a})`;
      ctx.stroke();

      // 细琥珀刻度
      ctx.strokeStyle = `rgba(${AMBER}, ${0.9 * a})`;
      ctx.lineWidth = isSel ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(cardX + 9, anchorY - 4);
      ctx.lineTo(cardX + 9, anchorY + 4);
      ctx.stroke();
      ctx.lineWidth = 1;

      // EN（mono 大写）+ 中文 · 规格
      ctx.textAlign = "left";
      ctx.font = isSel ? MONO_BOLD : MONO;
      ctx.fillStyle = isSel
        ? `rgba(${AMBER}, ${0.98 * a})`
        : `rgba(236, 241, 248, ${0.92 * a})`;
      ctx.fillText(e.name.toUpperCase(), cardX + 18, cardY + 12);

      ctx.font = SANS;
      ctx.fillStyle = `rgba(176, 186, 201, ${0.88 * a})`;
      const line2 = meta.spec ? `${meta.cn} · ${meta.spec}` : meta.cn;
      ctx.fillText(line2, cardX + 18, cardY + 25);
    }
    ctx.textBaseline = "alphabetic";
  }

  // ---- 选中高亮（拆解与否都画） ----
  function drawSelection() {
    if (!selected) return;
    const info = labels.get(selected);
    if (!info || !info.group) return;
    const p = project(partWorldPos(info));
    if (!p) return;

    const pulse = 0.5 + 0.5 * Math.sin(t * 3.2);
    const r = 12 + 2 * pulse;

    ctx.strokeStyle = `rgba(${AMBER}, 0.95)`;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.stroke();

    // 四向刻度
    ctx.lineWidth = 1.2;
    for (let i = 0; i < 4; i++) {
      const ang = (Math.PI / 2) * i + Math.PI / 4;
      ctx.beginPath();
      ctx.moveTo(p.x + Math.cos(ang) * (r + 3), p.y + Math.sin(ang) * (r + 3));
      ctx.lineTo(p.x + Math.cos(ang) * (r + 8), p.y + Math.sin(ang) * (r + 8));
      ctx.stroke();
    }
    ctx.lineWidth = 1;

    // 未拆解时补一个悬浮芯片标签（拆解时引线卡已显示，跳过避免重复）
    if (labelAlpha <= 0.01) {
      const meta = PART_LABELS[selected] || { cn: "", spec: "" };
      const text = meta.cn ? `${selected.toUpperCase()} · ${meta.cn}` : selected.toUpperCase();
      ctx.font = MONO_BOLD;
      const tw = ctx.measureText(text).width;
      const cw = tw + 22;
      const cx = Math.min(p.x + 18, W - cw - 12);
      const cy = Math.max(12, p.y - 34);

      ctx.fillStyle = "rgba(8, 10, 14, 0.82)";
      roundRect(cx, cy, cw, 24, 4);
      ctx.fill();
      ctx.strokeStyle = `rgba(${AMBER}, 0.6)`;
      ctx.stroke();

      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = `rgba(${AMBER}, 1)`;
      ctx.fillText(text, cx + 11, cy + 12);
      ctx.textBaseline = "alphabetic";
    }
  }

  // ---- 左下功率表 ----
  function drawGauge(dt) {
    if (W < 140 || H < 140) return;
    const cx = 64;
    const cy = H - 64;
    const r = 34;
    const target = exploded ? 1 : 0.45 + 0.12 * Math.sin(t * 1.5);
    gauge += (target - gauge) * Math.min(1, (dt || 0) * 4);

    const a0 = Math.PI * 0.75;
    const sweep = Math.PI * 1.5;

    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(64, 72, 86, 0.85)";
    ctx.beginPath();
    ctx.arc(cx, cy, r, a0, a0 + sweep);
    ctx.stroke();

    ctx.strokeStyle = exploded ? `rgba(${AMBER}, 0.95)` : `rgba(${ICE}, 0.8)`;
    ctx.beginPath();
    ctx.arc(cx, cy, r, a0, a0 + sweep * clamp01(gauge));
    ctx.stroke();

    // 刻度
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(120, 132, 150, 0.7)";
    for (let i = 0; i <= 4; i++) {
      const ang = a0 + (sweep * i) / 4;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * (r + 6), cy + Math.sin(ang) * (r + 6));
      ctx.lineTo(cx + Math.cos(ang) * (r + 10), cy + Math.sin(ang) * (r + 10));
      ctx.stroke();
    }

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = '600 14px ui-monospace, Menlo, Consolas, monospace';
    ctx.fillStyle = exploded ? `rgba(${AMBER}, 1)` : "rgba(226, 232, 240, 0.95)";
    ctx.fillText(String(Math.round(clamp01(gauge) * 100)), cx, cy - 3);
    ctx.font = TINY;
    ctx.fillStyle = exploded ? `rgba(${AMBER}, 0.9)` : `rgba(${TEXT_DIM}, 0.9)`;
    ctx.fillText(exploded ? "SYS/OPEN" : "SYS/STBY", cx, cy + 13);

    ctx.font = TINY;
    ctx.fillStyle = `rgba(${TEXT_DIM}, 0.85)`;
    ctx.fillText("PWR", cx, cy - r - 12);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.lineCap = "butt";
  }

  // ---- 公共 API ----
  function update(deltaSeconds) {
    if (disposed) return;
    const dt = deltaSeconds || 0;
    t += dt;
    resize(false);

    // 标签淡入 / 淡出
    const target = exploded ? 1 : 0;
    labelAlpha += (target - labelAlpha) * Math.min(1, dt * 5);
    if (Math.abs(target - labelAlpha) < 0.005) labelAlpha = target;

    ctx.clearRect(0, 0, W, H);
    drawLabels();
    drawSelection();
    drawGauge(dt);
  }

  function setSelected(partName) {
    selected = partName || null;
  }

  function setExploded(value) {
    const next = !!value;
    if (next === exploded) return;
    exploded = next;
    if (next) explodeT0 = t;
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    for (const u of unsubs) { try { u(); } catch { /* noop */ } }
    if (typeof window !== "undefined") window.removeEventListener("resize", onResize);
    ctx.clearRect(0, 0, W, H);
  }

  // 初始与 exploder 状态对齐（集成可能在拆解后才挂 HUD）
  if (typeof getExploder === "function") {
    try {
      const ex = getExploder();
      if (ex && ex.isExploded && ex.isExploded()) setExploded(true);
    } catch { /* noop */ }
  }

  resize(true);

  return { update, setSelected, setExploded, dispose };
}

// ---- 小工具 ----
function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
