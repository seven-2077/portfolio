// src/ui/panel.js —— 配置面板行为层（#panel 点击委托 / 滑杆 / 状态仓库 / 持久化）
//
// deps（由集成注入）:
//   { setPaint, PAINT_PRESETS, applyBackground, BACKGROUND_NAMES,
//     setPreset, setTurntable, exploder, accessories, registry }
//
// 职责:
//   - 按 DOM 契约委托 #panel 内所有按钮 / 滑杆（audio、rev 两个按钮归 Agent D 自理，本模块跳过）
//   - 滑杆 → setPaint（hue /360，其余 /100）+ <output> 文本 + emit paint:changed
//   - is-active / aria-pressed 视图同步；toggle-explode 按钮文字 拆解 ⇄ 装回
//   - part:pick → #part-readout "name · 中文 · role"
//   - 状态仓库 + localStorage('el-config') 持久化（安全 JSON 解析）
//   - exportConfigJson() → {version:1, paint, presetId, background, accessories}
//
// 纯函数（Node 可测）: normalizePaint / serializeConfig / parseConfig / DEFAULT_STATE
// 本模块顶层不做任何 DOM 访问；initPanel 在无 document 时降级为纯状态仓库。

import { emit, on } from "../events.js";
import { PART_LABELS } from "../hud.js";

export const STORAGE_KEY = "el-config";

export const DEFAULT_STATE = {
  // 喷漆状态为归一化刻度（与 paint.js 的 setPaint/PAINT_PRESETS 一致：hue 0-1）
  paint: { hue: 47 / 360, saturation: 0.9, metalness: 0.3, clearcoat: 0.85 },
  presetId: "lotus_yellow",
  background: "auto_show",
  accessories: { wheel: "forged", wing: "gt", skirts: "off", caliper: "red" },
  exploded: false,
};

const PAINT_KEYS = ["hue", "saturation", "metalness", "clearcoat"];
// 状态域（归一化）：hue 0-1（滑杆 0-360 在边界 ÷360），其余 0-1（滑杆 0-100 ÷100）
const PAINT_RANGE = { hue: [0, 1], saturation: [0, 1], metalness: [0, 1], clearcoat: [0, 1] };
// 原始滑杆域（raw clamp 用）
const PAINT_RAW_RANGE = { hue: [0, 360], saturation: [0, 100], metalness: [0, 100], clearcoat: [0, 100] };
const ACCESSORY_VALUES = {
  wheel: ["forged", "turbine", "petal"],
  wing: ["gt", "ducktail"],
  skirts: ["on", "off"],
  caliper: ["red", "gold", "black"],
};
// DOM 契约 id ↔ paint.js PAINT_PRESETS 实际 id 的别名
const PRESET_ALIASES = { racing_green: "track_green", track_green: "racing_green" };

// ---------------------------------------------------------------- 纯函数

function round4(v) {
  return Math.round(v * 1e4) / 1e4;
}

/** 把任意来源的喷漆参数收敛到合同范围（越界截断，非法值回默认），并做 4 位舍入 */
export function normalizePaint(paint) {
  const src = paint && typeof paint === "object" ? paint : {};
  const out = {};
  for (const key of PAINT_KEYS) {
    const [lo, hi] = PAINT_RANGE[key];
    const raw = src[key];
    // null / "" / undefined 经 Number() 会变 0，须先剔除，避免把「非法」误判成合法的 0
    const v = raw === null || raw === undefined || raw === "" ? NaN : Number(raw);
    out[key] = Number.isFinite(v) ? round4(Math.min(hi, Math.max(lo, v))) : round4(DEFAULT_STATE.paint[key]);
  }
  return out;
}

/** 配件映射收敛：只认合同内的键与取值，非法项回默认 */
export function normalizeAccessories(acc) {
  const src = acc && typeof acc === "object" ? acc : {};
  const out = {};
  for (const group of Object.keys(ACCESSORY_VALUES)) {
    const v = src[group];
    out[group] = ACCESSORY_VALUES[group].includes(v) ? v : DEFAULT_STATE.accessories[group];
  }
  return out;
}

/** 状态 → 可序列化配置（version:1；不含 exploded / turntable 等会话态） */
export function serializeConfig(state) {
  const src = state && typeof state === "object" ? state : {};
  return {
    version: 1,
    paint: normalizePaint(src.paint),
    presetId: typeof src.presetId === "string" && src.presetId ? src.presetId : DEFAULT_STATE.presetId,
    background: typeof src.background === "string" && src.background ? src.background : DEFAULT_STATE.background,
    accessories: normalizeAccessories(src.accessories),
  };
}

/** JSON 字符串（或对象）→ 状态；任何解析失败返回 null（不抛） */
export function parseConfig(raw) {
  let obj = raw;
  if (typeof raw === "string") {
    try { obj = JSON.parse(raw); } catch { return null; }
  }
  if (!obj || typeof obj !== "object") return null;
  return {
    paint: normalizePaint(obj.paint),
    presetId: typeof obj.presetId === "string" && obj.presetId ? obj.presetId : DEFAULT_STATE.presetId,
    background: typeof obj.background === "string" && obj.background ? obj.background : DEFAULT_STATE.background,
    accessories: normalizeAccessories(obj.accessories),
    exploded: false,
  };
}

// ---------------------------------------------------------------- 面板

export function initPanel(deps = {}) {
  const {
    setPaint, PAINT_PRESETS, applyBackground, BACKGROUND_NAMES,
    setPreset, setTurntable, exploder, accessories, registry,
  } = deps;

  const hasDoc = typeof document !== "undefined";
  const hasStorage = typeof localStorage !== "undefined";

  let root = null;
  let wired = false;
  let backgroundHandle = null; // applyBackground 返回的 {dispose}，切换时释放
  let cameraPreset = "front34"; // 相机机位仅会话态（不入持久化）
  let turntableOn = false;

  // ---- 状态仓库 ----
  const state = {
    paint: { ...DEFAULT_STATE.paint },
    presetId: DEFAULT_STATE.presetId,
    background: DEFAULT_STATE.background,
    accessories: { ...DEFAULT_STATE.accessories },
    exploded: false,
    turntable: false,
  };

  const saved = loadSaved();
  if (saved) {
    state.paint = saved.paint;
    state.presetId = saved.presetId;
    state.background = saved.background;
    state.accessories = saved.accessories;
  } else {
    // 无存档：以 paint 预设 lotus_yellow 为种子，保证 UI 与渲染一致
    const seed = findPreset("lotus_yellow") || (Array.isArray(PAINT_PRESETS) ? PAINT_PRESETS[0] : null);
    if (seed && seed.id) {
      state.presetId = seed.id;
      state.paint = coercePresetPaint(seed);
    }
  }

  // ---- 持久化 ----
  function loadSaved() {
    if (!hasStorage) return null;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return parseConfig(raw);
    } catch { return null; }
  }

  function save() {
    if (!hasStorage) return;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(serializeConfig(state))); }
    catch { /* 隐私模式等场景静默 */ }
  }

  function findPreset(id) {
    if (!Array.isArray(PAINT_PRESETS)) return null;
    const hit = PAINT_PRESETS.find((p) => p && p.id === id);
    if (hit) return hit;
    // 契约 id 与 paint.js 实际 id 的别名（racing_green ↔ track_green）
    const alt = PRESET_ALIASES[id];
    return alt ? PAINT_PRESETS.find((p) => p && p.id === alt) || null : null;
  }

  // 预设参数 → 喷漆参数（宽容处理 0-100 与 0-1 两种刻度；hue 可能是角度）
  function coercePresetPaint(preset) {
    const out = {};
    for (const key of PAINT_KEYS) {
      let v = Number(preset[key]);
      if (!Number.isFinite(v)) v = DEFAULT_STATE.paint[key];
      if (key !== "hue" && v > 1) v = v / 100; // 饱和度/金属度/清漆若按百分比给
      if (key === "hue" && v > 1) v = v / 360; // hue 若按角度给 → 归一化
      out[key] = v;
    }
    return normalizePaint(out);
  }

  // ---- DOM 工具 ----
  function ensureRoot() {
    if (!hasDoc) return null;
    if (!root || !root.isConnected) root = document.getElementById("panel");
    return root;
  }

  function activate(button, selector) {
    const r = ensureRoot();
    if (!r || !button) return;
    for (const other of r.querySelectorAll(selector)) other.classList.remove("is-active");
    button.classList.add("is-active");
  }

  function rawValueOf(param, unitValue) {
    return param === "hue" ? Math.round(unitValue * 360) : Math.round(unitValue * 100);
  }

  function updateOutput(input) {
    const param = input.dataset.param;
    const out = input.nextElementSibling && input.nextElementSibling.tagName === "OUTPUT"
      ? input.nextElementSibling
      : (input.parentElement && input.parentElement.querySelector("output"));
    if (!out) return;
    const raw = rawValueOf(param, state.paint[param]);
    out.textContent = param === "hue" ? `${raw}°` : `${raw}%`;
  }

  function syncRanges() {
    const r = ensureRoot();
    if (!r) return;
    for (const input of r.querySelectorAll('input[type="range"][data-paint]')) {
      const param = input.dataset.param;
      if (!PAINT_KEYS.includes(param)) continue;
      input.value = String(rawValueOf(param, state.paint[param]));
      updateOutput(input);
    }
  }

  function syncPaintPresetButtons() {
    const r = ensureRoot();
    if (!r) return;
    for (const btn of r.querySelectorAll('[data-action="paint-preset"]')) {
      btn.classList.toggle("is-active", btn.dataset.presetId === state.presetId);
    }
  }

  function syncBackgroundButtons() {
    const r = ensureRoot();
    if (!r) return;
    for (const btn of r.querySelectorAll('[data-action="background"]')) {
      btn.classList.toggle("is-active", btn.dataset.bg === state.background);
    }
  }

  function syncAccessoryButtons() {
    const r = ensureRoot();
    if (!r) return;
    for (const btn of r.querySelectorAll("[data-accessory]")) {
      const group = btn.dataset.group;
      const value = btn.dataset.value;
      if (value) {
        btn.classList.toggle("is-active", state.accessories[group] === value);
      } else if (group === "skirts") {
        btn.classList.toggle("is-active", state.accessories.skirts === "on");
      }
    }
  }

  function syncCameraButtons() {
    const r = ensureRoot();
    if (!r) return;
    for (const btn of r.querySelectorAll('[data-action="preset"]')) {
      btn.classList.toggle("is-active", btn.dataset.preset === cameraPreset);
    }
  }

  function syncTurntableButton() {
    const r = ensureRoot();
    if (!r) return;
    const btn = r.querySelector('[data-action="turntable"]');
    if (btn) btn.setAttribute("aria-pressed", String(turntableOn));
  }

  function syncExplodeButton() {
    const r = ensureRoot();
    if (!r) return;
    const btn = r.querySelector('[data-action="toggle-explode"]');
    if (btn) btn.textContent = state.exploded ? "装回" : "拆解";
  }

  function fillReadout(name) {
    const el = hasDoc ? document.getElementById("part-readout") : null;
    if (!el) return;
    if (!name) { el.textContent = "—"; return; }
    const meta = PART_LABELS[name] || { cn: name };
    let role = "—";
    if (registry && typeof registry.get === "function") {
      const info = registry.get(name);
      if (info && info.materialRole) role = info.materialRole;
    }
    el.textContent = `${name} · ${meta.cn} · ${role}`;
  }

  // ---- 喷漆 ----
  function applyPaint(emitChange) {
    if (typeof setPaint === "function") {
      try { setPaint({ ...state.paint }); }
      catch (err) { console.error("[panel] setPaint failed:", err); }
    }
    if (emitChange) emit("paint:changed", { ...state.paint });
  }

  function onRangeInput(e) {
    const input = e.target;
    // data-paint 可能无值（契约只保证属性存在），用 in 判断
    if (!input || !input.dataset || !("paint" in input.dataset)) return;
    const param = input.dataset.param;
    if (!PAINT_KEYS.includes(param)) return;
    const raw = Number(input.value);
    const [lo, hi] = PAINT_RAW_RANGE[param]; // 原始滑杆域：hue 0-360，其余 0-100
    const v = Number.isFinite(raw) ? raw : lo;
    const clamped = Math.min(hi, Math.max(lo, v));
    state.paint[param] = round4(clamped / hi); // → 归一化状态（与 setPaint 同刻度）
    updateOutput(input);
    state.presetId = "";
    syncPaintPresetButtons();
    applyPaint(true);
    save();
  }

  // ---- 配件 ----
  function onAccessoryChanged(payload) {
    const group = payload && payload.group;
    const value = payload && payload.value;
    if (!group || !(group in state.accessories)) return;
    state.accessories[group] = value;
    syncAccessoryButtons();
    save();
  }

  function handleAccessoryButton(btn) {
    // data-group 缺省时按动作名推断（toggle-skirts → skirts 组）
    const group = btn.dataset.group || (btn.dataset.action === "toggle-skirts" ? "skirts" : null);
    if (!group || !(group in ACCESSORY_VALUES)) return;
    let value = btn.dataset.value;
    if (!value && group === "skirts") {
      value = state.accessories.skirts === "on" ? "off" : "on";
    }
    if (!value || !ACCESSORY_VALUES[group].includes(value)) return;
    if (accessories && typeof accessories.setGroup === "function" && accessories.setGroup(group, value)) {
      // setGroup 成功即更新视图（不依赖 accessory:changed 事件；事件回调幂等）
      state.accessories[group] = value;
      syncAccessoryButtons();
      save();
    }
    emit("audio:tick", { action: `accessory:${group}` });
  }

  // ---- 按钮点击委托 ----
  function onClick(e) {
    const btn = e.target && e.target.closest ? e.target.closest("button") : null;
    const r = ensureRoot();
    if (!btn || !r || !r.contains(btn)) return;

    const action = btn.dataset.action;

    // Agent D 自接线的两个按钮：完全不碰（也不发 tick，避免双响）
    if (action === "audio" || action === "rev") return;

    // data-accessory 可能无值（契约只保证属性存在），用 in 判断
    if ("accessory" in btn.dataset || action === "toggle-skirts") {
      handleAccessoryButton(btn);
      return;
    }

    switch (action) {
      case "preset": {
        const name = btn.dataset.preset;
        if (!name) return;
        cameraPreset = name;
        syncCameraButtons();
        emit("preset:before", { name }); // 语义上先于切换
        if (typeof setPreset === "function") {
          try { setPreset(name); } catch (err) { console.error("[panel] setPreset failed:", err); }
        }
        break;
      }
      case "turntable": {
        turntableOn = !turntableOn;
        state.turntable = turntableOn;
        syncTurntableButton();
        if (typeof setTurntable === "function") {
          try { setTurntable(turntableOn); } catch (err) { console.error("[panel] setTurntable failed:", err); }
        }
        break;
      }
      case "toggle-explode": {
        if (exploder && typeof exploder.toggle === "function") exploder.toggle();
        break;
      }
      case "paint-preset": {
        const id = btn.dataset.presetId;
        const preset = findPreset(id);
        if (!preset) return;
        state.presetId = id;
        state.paint = coercePresetPaint(preset);
        syncRanges();
        syncPaintPresetButtons();
        applyPaint(true);
        save();
        break;
      }
      case "background": {
        const name = btn.dataset.bg;
        if (!name) return;
        if (Array.isArray(BACKGROUND_NAMES) && !BACKGROUND_NAMES.includes(name)) return;
        state.background = name;
        if (backgroundHandle && typeof backgroundHandle.dispose === "function") {
          try { backgroundHandle.dispose(); } catch { /* noop */ }
          backgroundHandle = null;
        }
        if (typeof applyBackground === "function") {
          try { backgroundHandle = applyBackground(name) || null; }
          catch (err) { console.error("[panel] applyBackground failed:", err); }
        }
        syncBackgroundButtons();
        emit("background:switch", { name });
        save();
        break;
      }
      default:
        return; // 未知动作不发 tick
    }
    emit("audio:tick", { action: action || "panel" });
  }

  // ---- 事件订阅 ----
  const unsubs = [];
  function subscribe() {
    unsubs.push(on("explode:start", () => { state.exploded = true; syncExplodeButton(); }));
    unsubs.push(on("assemble:start", () => { state.exploded = false; syncExplodeButton(); }));
    unsubs.push(on("part:pick", (payload) => {
      const name = payload && typeof payload === "object" ? payload.name : payload;
      fillReadout(name || null);
    }));
    unsubs.push(on("accessory:changed", onAccessoryChanged));
  }

  // ---- 视图全量同步 ----
  function updateDom(next) {
    if (next && typeof next === "object") {
      if (next.paint) state.paint = normalizePaint(next.paint);
      if (next.presetId) state.presetId = next.presetId;
      if (next.background) state.background = next.background;
      if (next.accessories) state.accessories = normalizeAccessories(next.accessories);
      if (typeof next.exploded === "boolean") state.exploded = next.exploded;
    }
    syncRanges();
    syncPaintPresetButtons();
    syncBackgroundButtons();
    syncAccessoryButtons();
    syncCameraButtons();
    syncTurntableButton();
    syncExplodeButton();
  }

  function getState() {
    return {
      paint: { ...state.paint },
      presetId: state.presetId,
      background: state.background,
      accessories: { ...state.accessories },
      exploded: state.exploded,
      turntable: turntableOn,
    };
  }

  function exportConfigJson() {
    return serializeConfig(state);
  }

  function dispose() {
    for (const u of unsubs) { try { u(); } catch { /* noop */ } }
    unsubs.length = 0;
    const r = ensureRoot();
    if (r && wired) {
      r.removeEventListener("click", onClick);
      r.removeEventListener("input", onRangeInput);
    }
    wired = false;
    if (backgroundHandle && typeof backgroundHandle.dispose === "function") {
      try { backgroundHandle.dispose(); } catch { /* noop */ }
    }
    backgroundHandle = null;
  }

  // ---- 启动 ----
  subscribe();

  if (ensureRoot() && !wired) {
    root.addEventListener("click", onClick);
    root.addEventListener("input", onRangeInput);
    wired = true;
  }

  // 恢复渲染侧：喷漆恒应用（保证 UI 与画面一致）；背景仅在有存档时应用（避免首访双背景）
  applyPaint(false);
  if (saved && typeof applyBackground === "function") {
    try { backgroundHandle = applyBackground(state.background) || null; }
    catch (err) { console.error("[panel] applyBackground(init) failed:", err); }
  }
  if (accessories && typeof accessories.setGroup === "function") {
    for (const group of Object.keys(ACCESSORY_VALUES)) {
      try { accessories.setGroup(group, state.accessories[group]); }
      catch { /* noop */ }
    }
  }

  updateDom();

  return { updateDom, getState, exportConfigJson, dispose };
}
