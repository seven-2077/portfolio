// tests/config.test.js —— 配置序列化往返 / 参数截断 / 无 DOM 降级
import test from "node:test";
import assert from "node:assert/strict";
import {
  serializeConfig,
  parseConfig,
  normalizePaint,
  normalizeAccessories,
  DEFAULT_STATE,
  STORAGE_KEY,
  initPanel,
} from "../src/ui/panel.js";

const FIXTURE = {
  paint: { hue: 0.5958, saturation: 0.62, metalness: 0.31, clearcoat: 0.88 },
  presetId: "meteor_grey",
  background: "night_road",
  accessories: { wheel: "turbine", wing: "ducktail", skirts: "on", caliper: "gold" },
  exploded: true, // 会话态：不应进导出配置
};

test("serialize → JSON → parse 往返一致，且 version=1", () => {
  const cfg = serializeConfig(FIXTURE);
  assert.equal(cfg.version, 1);
  assert.equal(cfg.exploded, undefined, "会话态 exploded 不入配置");
  assert.equal(STORAGE_KEY, "el-config");

  const json = JSON.stringify(cfg);
  const back = parseConfig(json);
  assert.ok(back, "往返解析不应为 null");
  assert.deepEqual(serializeConfig(back), cfg, "往返后序列化结果应逐字段相等");
});

test("越界喷漆参数被截断到合同范围（状态域 0-1）", () => {
  const low = serializeConfig({ paint: { hue: -40, saturation: 3, metalness: -1, clearcoat: 999 } });
  assert.deepEqual(low.paint, { hue: 0, saturation: 1, metalness: 0, clearcoat: 1 });

  const high = serializeConfig({ paint: { hue: 400, saturation: 150, metalness: 50, clearcoat: 200 } });
  assert.deepEqual(high.paint, { hue: 1, saturation: 1, metalness: 1, clearcoat: 1 });

  // 边界值原样保留
  const edge = serializeConfig({ paint: { hue: 0.66, saturation: 0, metalness: 1, clearcoat: 0 } });
  assert.deepEqual(edge.paint, { hue: 0.66, saturation: 0, metalness: 1, clearcoat: 0 });
});

test("非数值喷漆参数回退默认值", () => {
  const cfg = serializeConfig({
    paint: { hue: "abc", saturation: NaN, metalness: Infinity, clearcoat: null },
  });
  assert.deepEqual(cfg.paint, normalizePaint(DEFAULT_STATE.paint));
  for (const v of Object.values(cfg.paint)) assert.ok(Number.isFinite(v));
});

test("非法配件取值回默认；非法 JSON 安全返回 null", () => {
  const cfg = serializeConfig({
    accessories: { wheel: "chrome", wing: null, skirts: "maybe", caliper: "blue", extra: 1 },
  });
  assert.deepEqual(cfg.accessories, DEFAULT_STATE.accessories);
  assert.deepEqual(normalizeAccessories(undefined), DEFAULT_STATE.accessories);

  assert.equal(parseConfig("{not json"), null);
  assert.equal(parseConfig(42), null);
  assert.equal(parseConfig(null), null);
});

test("initPanel 在无 DOM 环境下降级为纯状态仓库", () => {
  const panel = initPanel({});
  const st = panel.getState();
  assert.equal(typeof st.paint.hue, "number");
  assert.equal(typeof st.exploded, "boolean");

  const exported = panel.exportConfigJson();
  assert.equal(exported.version, 1);
  assert.deepEqual(serializeConfig(exported), exported);

  // updateDom 外部注入状态（归一化刻度） → getState / export 同步
  panel.updateDom({
    paint: { hue: 0.3333, saturation: 0.5, metalness: 0.2, clearcoat: 0.9 },
    presetId: "racing_green",
    background: "wind_tunnel",
    accessories: { wheel: "petal", wing: "gt", skirts: "on", caliper: "black" },
    exploded: true,
  });
  const st2 = panel.getState();
  assert.equal(st2.presetId, "racing_green");
  assert.equal(st2.background, "wind_tunnel");
  assert.equal(st2.accessories.wheel, "petal");
  assert.equal(st2.exploded, true);
  assert.deepEqual(panel.exportConfigJson().paint, {
    hue: 0.3333, saturation: 0.5, metalness: 0.2, clearcoat: 0.9,
  });

  panel.dispose();
});
