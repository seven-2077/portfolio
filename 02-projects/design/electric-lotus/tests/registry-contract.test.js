// tests/registry-contract.test.js —— body.js 注册表冻结合同校验
//
// body.js 由并行 agent 编写：文件缺失 → skip；存在但半写（导入/构建抛错）→ 有限重试。
// 测试本身的断言严格按合同，不做任何放水。

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const bodyPath = path.join(here, "..", "src", "body.js");

const EXPECTED = [
  "shell", "hood_front", "door_left", "door_right", "canopy",
  "band_left", "band_right", "wing_rear", "diffuser_rear",
  "wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR",
  "battery_pack", "seat_center", "seat_left", "seat_right",
  "light_front_left", "light_front_right", "light_rear_bar",
];

const EXPLODE_CONTRACT = {
  hood_front: "hinge_up",
  door_left: "gullwing",
  door_right: "gullwing",
  canopy: "lift_tilt",
  band_left: "slide_lateral",
  band_right: "slide_lateral",
  wing_rear: "lift_back",
  diffuser_rear: "slide_back",
  wheel_FL: "spin_out",
  wheel_FR: "spin_out",
  wheel_RL: "spin_out",
  wheel_RR: "spin_out",
  battery_pack: "drop_down",
  seat_center: "rail_up",
  seat_left: "rail_up",
  seat_right: "rail_up",
  light_front_left: "slide_forward",
  light_front_right: "slide_forward",
  light_rear_bar: "slide_back",
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 导入 + buildCar 都可能踩到半写状态 → 带缓存穿透的有限重试 */
async function buildOnce() {
  let lastErr;
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const mod = await import(`../src/body.js?retry=${attempt}`);
      if (typeof mod.buildCar !== "function") throw new Error("buildCar 不是函数");
      return mod.buildCar();
    } catch (err) {
      lastErr = err;
      await sleep(300);
    }
  }
  throw lastErr;
}

test("body.js 注册表符合冻结合同", async (t) => {
  if (!fs.existsSync(bodyPath)) {
    t.skip("src/body.js 尚未落盘（并行编写中）");
    return;
  }

  const { carRoot, registry } = await buildOnce();

  assert.ok(carRoot && carRoot.isObject3D, "carRoot 应为 Object3D");
  assert.ok(registry instanceof Map, "registry 应为 Map<string, PartInfo>");

  // 恰好 20 个合同零件名
  assert.equal(registry.size, 20, "注册表应恰含 20 项");
  assert.deepEqual([...registry.keys()].sort(), [...EXPECTED].sort());

  for (const name of EXPECTED) {
    const info = registry.get(name);
    assert.ok(info, `${name} 缺失`);
    assert.equal(info.name, name, `${name}.name 应自洽`);
    assert.ok(info.group && info.group.isObject3D, `${name}.group 应为 Object3D`);
    assert.equal(typeof info.materialRole, "string", `${name}.materialRole 应为字符串`);

    const ex = info.explode;
    assert.ok(ex && typeof ex === "object", `${name}.explode 缺失`);
    if (name === "shell") {
      assert.equal(ex.static, true, "shell 应为 static");
      assert.equal(ex.type, undefined, "shell 不应有 type");
    } else {
      assert.equal(ex.type, EXPLODE_CONTRACT[name], `${name}.explode.type 违约`);
    }
  }

  // 车身尺寸元数据
  const d = carRoot.userData && carRoot.userData.dimensions;
  assert.ok(d, "carRoot.userData.dimensions 缺失");
  assert.ok(d.length > 0 && d.width > 0 && d.height > 0, "dimensions 应为正数");

  // 每个网格都带 userData.partName + userData.materialRole
  const meshes = [];
  carRoot.traverse((o) => { if (o.isMesh) meshes.push(o); });
  assert.ok(meshes.length >= 20, `至少应有 20 个网格，实际 ${meshes.length}`);
  for (const m of meshes) {
    assert.ok(
      m.userData && typeof m.userData.partName === "string" && m.userData.partName,
      `网格 ${m.name || "<unnamed>"} 缺 userData.partName`,
    );
    assert.ok(
      m.userData && typeof m.userData.materialRole === "string" && m.userData.materialRole,
      `网格 ${m.name || "<unnamed>"} 缺 userData.materialRole`,
    );
  }

  // 四轮各含 rim 子组 + tire 网格
  for (const w of ["wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR"]) {
    const g = registry.get(w).group;
    let rim = null;
    let tire = null;
    g.traverse((o) => {
      if (!rim && o.isGroup && (o.userData.subRole === "rim" || o.name === "rim")) rim = o;
      if (!tire && o.isMesh && o.name === "tire") tire = o;
    });
    assert.ok(rim, `${w} 缺 rim 子组`);
    assert.ok(tire, `${w} 缺名为 tire 的网格`);
  }
});
