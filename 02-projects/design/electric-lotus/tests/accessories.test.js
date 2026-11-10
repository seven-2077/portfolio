// tests/accessories.test.js —— 配件状态机 + 变体换装（纯 three，无 DOM）
import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import {
  initAccessories,
  ACCESSORY_DEFAULTS,
  ACCESSORY_VALUES,
  CALIPER_COLORS,
} from "../src/accessories.js";
import { on } from "../src/events.js";

/** 合同形状的最小假注册表：四轮（rim+tire）+ 尾翼 + 车身 */
function fakeRegistry() {
  const reg = new Map();

  for (const name of ["wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR"]) {
    const wheel = new THREE.Group();
    wheel.name = name;
    const rim = new THREE.Group();
    rim.name = "rim";
    rim.userData.subRole = "rim";
    rim.userData.partName = name;
    const spoke = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.04, 0.05));
    spoke.name = "spoke_orig";
    rim.add(spoke);
    const tire = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.09, 8, 24));
    tire.name = "tire";
    wheel.add(rim, tire);
    reg.set(name, { name, group: wheel, materialRole: "wheel", explode: { type: "spin_out" } });
  }

  const wing = new THREE.Group();
  wing.name = "wing_rear";
  wing.add(new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.04, 0.3)));
  reg.set("wing_rear", { name: "wing_rear", group: wing, materialRole: "aero", explode: { type: "lift_back" } });

  const shell = new THREE.Group();
  shell.name = "shell";
  shell.add(new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.75, 4.3)));
  reg.set("shell", { name: "shell", group: shell, materialRole: "body", explode: { static: true } });

  return reg;
}

function findRim(wheelGroup) {
  let rim = null;
  wheelGroup.traverse((o) => { if (!rim && o.isGroup && (o.userData.subRole === "rim" || o.name === "rim")) rim = o; });
  return rim;
}

const WHEELS = ["wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR"];

test("状态机：setGroup / getActive / 事件契约", () => {
  const acc = initAccessories({ registry: fakeRegistry() });
  assert.deepEqual(acc.getActive(), ACCESSORY_DEFAULTS);

  const events = [];
  const un = on("accessory:changed", (e) => events.push(e));

  assert.equal(acc.setGroup("wheel", "turbine"), true);
  assert.equal(acc.getActive().wheel, "turbine");
  assert.deepEqual(events.at(-1), { group: "wheel", value: "turbine" });

  // 非法值 / 非法组 → false、状态不变、不发事件
  assert.equal(acc.setGroup("wheel", "chrome"), false);
  assert.equal(acc.setGroup("exhaust", "loud"), false);
  assert.equal(acc.getActive().wheel, "turbine");
  assert.equal(events.length, 1);

  // 幂等：同值 → true 但不重复发事件
  assert.equal(acc.setGroup("wheel", "turbine"), true);
  assert.equal(events.length, 1);

  assert.equal(acc.setGroup("caliper", "gold"), true);
  assert.deepEqual(events.at(-1), { group: "caliper", value: "gold" });

  // getActive 返回副本，外部改动不污染内部状态
  const snapshot = acc.getActive();
  snapshot.wheel = "petal";
  assert.equal(acc.getActive().wheel, "turbine");

  // 合同值域完整
  for (const group of Object.keys(ACCESSORY_VALUES)) {
    for (const value of ACCESSORY_VALUES[group]) {
      assert.equal(acc.setGroup(group, value), true, `${group}/${value} 应被接受`);
      assert.equal(acc.getActive()[group], value);
    }
  }

  un();
});

test("轮毂变体换装进 rim 组（原辐条隐藏、旧变体清理）", () => {
  const reg = fakeRegistry();
  const acc = initAccessories({ registry: reg });

  const checkKind = (kind) => {
    for (const w of WHEELS) {
      const rim = findRim(reg.get(w).group);
      assert.ok(rim, `${w} 应有 rim 组`);
      const variants = rim.children.filter((c) => c.userData.isRimVariant);
      assert.equal(variants.length, 1, `${w} 应恰有 1 个变体`);
      assert.equal(variants[0].userData.variantKind, kind);
      const orig = rim.children.find((c) => c.name === "spoke_orig");
      assert.ok(orig, "原辐条应保留（仅隐藏）");
      assert.equal(orig.visible, false, "原辐条应隐藏");
      // 变体网格带 partName
      let meshes = 0;
      let named = 0;
      variants[0].traverse((o) => {
        if (o.isMesh) { meshes++; if (o.userData.partName === w) named++; }
      });
      assert.ok(meshes > 0, "变体应含网格");
      assert.equal(named, meshes, "变体网格应带本轮 partName");
    }
  };

  checkKind("forged"); // 默认已生效
  assert.equal(acc.setGroup("wheel", "petal"), true);
  checkKind("petal");
  assert.equal(acc.setGroup("wheel", "turbine"), true);
  checkKind("turbine");
});

test("卡钳：缺失时生成 4 个并按值热改色", () => {
  const reg = fakeRegistry();
  const acc = initAccessories({ registry: reg });

  const collect = () => {
    const out = [];
    for (const w of WHEELS) {
      reg.get(w).group.traverse((o) => {
        if (o.isMesh && o.userData.subRole === "caliper") out.push({ w, mesh: o });
      });
    }
    return out;
  };

  let calipers = collect();
  assert.equal(calipers.length, 4, "四轮各应有 1 个卡钳");
  for (const c of calipers) {
    assert.ok(c.mesh.userData.partName.startsWith("wheel_"), "卡钳应带轮组 partName");
    assert.ok(c.mesh.parent, "卡钳必须挂在场景图内");
    assert.equal(c.mesh.material.color.getHex(), CALIPER_COLORS.red, "默认红");
  }

  assert.equal(acc.setGroup("caliper", "gold"), true);
  calipers = collect();
  assert.equal(calipers.length, 4, "换色不应产生重复卡钳");
  for (const c of calipers) assert.equal(c.mesh.material.color.getHex(), CALIPER_COLORS.gold);

  acc.setGroup("caliper", "black");
  for (const c of collect()) assert.equal(c.mesh.material.color.getHex(), CALIPER_COLORS.black);
});

test("侧裙 on/off 可见性切换", () => {
  const reg = fakeRegistry();
  const acc = initAccessories({ registry: reg });
  const shell = reg.get("shell").group;

  const holderOf = () => shell.children.find((c) => c.userData.isSkirtHolder);

  // 默认 off：holder 存在与否都应不可见
  const initial = holderOf();
  if (initial) assert.equal(initial.visible, false);

  assert.equal(acc.setGroup("skirts", "on"), true);
  const holder = holderOf();
  assert.ok(holder, "开启后应生成侧裙 holder");
  assert.equal(holder.visible, true);
  assert.ok(holder.children.length >= 2, "应有左右两片侧刃");
  for (const blade of holder.children) assert.equal(blade.visible, true);

  assert.equal(acc.setGroup("skirts", "off"), true);
  assert.equal(holder.visible, false);
});

test("尾翼 gt / ducktail 换装（home pivot 不动）", () => {
  const reg = fakeRegistry();
  const acc = initAccessories({ registry: reg });
  const wing = reg.get("wing_rear").group;
  const homePos = wing.position.clone();

  const orig = wing.children.find((c) => !c.userData.isWingVariant);
  assert.ok(orig, "原翼面应保留（仅隐藏）");
  assert.equal(orig.visible, false, "gt 生效后原翼面隐藏");

  let variants = wing.children.filter((c) => c.userData.isWingVariant);
  assert.equal(variants.length, 1);

  assert.equal(acc.setGroup("wing", "ducktail"), true);
  variants = wing.children.filter((c) => c.userData.isWingVariant);
  assert.equal(variants.length, 1, "旧变体应被清理");
  assert.equal(variants[0].userData.variantKind, "ducktail");

  // 变体只加子节点，wing 组自身位姿（拆解 home pivot）保持不变
  assert.ok(wing.position.equals(homePos), "wing home pivot 不应被改动");
});
