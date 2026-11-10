/* 电莲花 electric-lotus —— 应用入口（整合层）
 *
 * 装配顺序（Phase 3）：
 *   舞台 initScene → 车体 buildCar + applyRoles → 配件/拆解 → 背景
 *   → HUD → 音频（自接线）→ 面板 initPanel → 拾取 → 帧循环
 *
 * 事件总线（src/events.js）承担模块间大部分通信：
 *   explode:start / assemble:start / part:pick / part:seated /
 *   accessory:changed / paint:changed / background:switch / audio:tick
 */
import { initScene } from "./scene.js";
import { buildCar } from "./body.js";
import { applyRoles, setPaint, PAINT_PRESETS } from "./materials/paint.js";
import {
  setRenderer as setBackgroundRenderer,
  applyBackground,
  BACKGROUND_NAMES,
} from "./backgrounds.js";
import { initExplode } from "./explode.js";
import { initAccessories } from "./accessories.js";
import { initHud } from "./hud.js";
import { initPanel, DEFAULT_STATE } from "./ui/panel.js";
import { initAudio } from "./audio/engine.js";
import { exportGLB, exportJSON } from "./export/gltf.js";
import { emit } from "./events.js";

/* ---- 舞台 ---- */
const stage = initScene(document.getElementById("root"));
const { renderer, scene, camera, controls } = stage;

/* ---- 车体（20 零件 registry + 角色材质换装） ---- */
const { carRoot, registry } = buildCar();
applyRoles(carRoot);
scene.add(carRoot);
stage.setPickTarget(carRoot); // 转盘轴心 + 拾取目标

/* ---- 配件系统 / 拆解编排 ---- */
const accessories = initAccessories({ registry });
const exploder = initExplode({ registry, camera, controls });

/* ---- 背景（默认车展大厅；面板切换时模块内部先释放旧 rig） ---- */
setBackgroundRenderer(renderer);
applyBackground(scene, DEFAULT_STATE.background, renderer);

/* ---- HUD（事件自接线，缺画布时安全 no-op） ---- */
const hud = initHud({
  camera,
  renderer,
  registry,
  getExploder: () => exploder,
});

/* ---- 音频（事件总线 + data-action="audio"/"rev" 按钮自接线） ---- */
const audio = initAudio();

/* ---- 控制面板 ---- */
const panel = initPanel({
  setPaint,
  PAINT_PRESETS,
  applyBackground: (name) => applyBackground(scene, name, renderer),
  BACKGROUND_NAMES,
  setPreset: stage.setPreset,
  setTurntable: stage.setTurntable,
  exploder,
  accessories,
  registry,
});

/* ---- 拾取：pointerdown→pointerup 位移阈值区分点击与轨道拖拽 ---- */
let downAt = null;
renderer.domElement.addEventListener("pointerdown", (e) => {
  downAt = { x: e.clientX, y: e.clientY, t: performance.now() };
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downAt) return;
  const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
  const held = performance.now() - downAt.t;
  downAt = null;
  if (moved > 6 || held > 400) return; // 拖拽 / 长按不触发拾取
  const rect = renderer.domElement.getBoundingClientRect();
  const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  const name = stage.pickPart(ndcX, ndcY);
  emit("part:pick", { name: name || null });
});

/* ---- 导出按钮（panel 对未知 action 直接 return，不冲突） ---- */
const panelRoot = document.getElementById("panel");
if (panelRoot) {
  panelRoot.addEventListener("click", (e) => {
    const btn = e.target && e.target.closest ? e.target.closest("button") : null;
    if (!btn) return;
    if (btn.dataset.action === "export-glb") {
      exportGLB(carRoot).catch((err) => console.error("[export] GLB failed:", err));
    } else if (btn.dataset.action === "export-config") {
      exportJSON(panel.exportConfigJson());
    }
  });
}

/* ---- 帧循环：拆解编排 + HUD + 音频 ---- */
stage.onFrame((_t, dt) => {
  exploder.update(dt);
  hud.update(dt);
  if (audio && typeof audio.update === "function") audio.update(dt);
});

/* ---- 首帧渲染后收起开屏遮罩 ---- */
const offFirstFrame = stage.onFrame(() => {
  offFirstFrame();
  const splash = document.getElementById("splash");
  if (splash) splash.classList.add("is-hidden");
});

/* ---- 调试/验收钩子 ---- */
window.__electricLotus = {
  ready: true,
  stage,
  registry,
  panel,
  exploder,
  accessories,
  hud,
  audio,
};
