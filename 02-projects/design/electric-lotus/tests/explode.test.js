// tests/explode.test.js —— 拆解编排端到端（无渲染、无 DOM，纯 three 对象）
//
// 验证: 事件时序 / shell 静止 / phyllotaxis 终点落位 / 装回归位 + part:seated /
//       相机 ×1.35 后撤与 FOV 35→30 往返 / toggle 与重复调用语义。
import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { initExplode, phyllotaxisAngle, phyllotaxisRadius } from "../src/explode.js";
import { on } from "../src/events.js";

const DEG = Math.PI / 180;

// fakeCar 布局的 home 快照（与 layout 一一对应）
const HOME = {
  shell: [0, 0.5, 0],
  hood_front: [0, 0.7, 1.5],
  door_left: [-0.95, 0.7, 0.1],
  door_right: [0.95, 0.7, 0.1],
  canopy: [0, 0.95, 0.2],
  band_left: [-1.0, 0.5, 0],
  band_right: [1.0, 0.5, 0],
  wing_rear: [0, 0.85, -1.9],
  diffuser_rear: [0, 0.3, -2.0],
  wheel_FL: [-0.9, 0.33, 1.45],
  wheel_FR: [0.9, 0.33, 1.45],
  wheel_RL: [-0.9, 0.33, -1.45],
  wheel_RR: [0.9, 0.33, -1.45],
  battery_pack: [0, 0.25, 0],
  seat_center: [0, 0.6, -0.2],
  seat_left: [-0.4, 0.6, -0.2],
  seat_right: [0.4, 0.6, -0.2],
  light_front_left: [-0.7, 0.55, 2.1],
  light_front_right: [0.7, 0.55, 2.1],
  light_rear_bar: [0, 0.6, -2.1],
};

/** 合同 20 件的最小假车（carRoot 局部空间 = 车空间: L=+X, F=+Z, U=+Y） */
function fakeCar() {
  const carRoot = new THREE.Group();
  carRoot.userData.dimensions = { length: 4.5, width: 2.0, height: 1.15 };

  const layout = [
    ["shell", 0, 0.5, 0, "static"],
    ["hood_front", 0, 0.7, 1.5, "hinge_up"],
    ["door_left", -0.95, 0.7, 0.1, "gullwing"],
    ["door_right", 0.95, 0.7, 0.1, "gullwing"],
    ["canopy", 0, 0.95, 0.2, "lift_tilt"],
    ["band_left", -1.0, 0.5, 0, "slide_lateral"],
    ["band_right", 1.0, 0.5, 0, "slide_lateral"],
    ["wing_rear", 0, 0.85, -1.9, "lift_back"],
    ["diffuser_rear", 0, 0.3, -2.0, "slide_back"],
    ["wheel_FL", -0.9, 0.33, 1.45, "spin_out"],
    ["wheel_FR", 0.9, 0.33, 1.45, "spin_out"],
    ["wheel_RL", -0.9, 0.33, -1.45, "spin_out"],
    ["wheel_RR", 0.9, 0.33, -1.45, "spin_out"],
    ["battery_pack", 0, 0.25, 0, "drop_down"],
    ["seat_center", 0, 0.6, -0.2, "rail_up"],
    ["seat_left", -0.4, 0.6, -0.2, "rail_up"],
    ["seat_right", 0.4, 0.6, -0.2, "rail_up"],
    ["light_front_left", -0.7, 0.55, 2.1, "slide_forward"],
    ["light_front_right", 0.7, 0.55, 2.1, "slide_forward"],
    ["light_rear_bar", 0, 0.6, -2.1, "slide_back"],
  ];

  const registry = new Map();
  for (const [name, x, y, z, type] of layout) {
    const group = new THREE.Group();
    group.name = name;
    group.position.set(x, y, z);
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.2, 0.4));
    mesh.name = `${name}_mesh`;
    group.add(mesh);
    carRoot.add(group);
    registry.set(name, {
      name,
      group,
      materialRole: "body",
      explode: type === "static" ? { static: true } : { type },
    });
  }
  return { carRoot, registry };
}

function makeRig() {
  const { carRoot, registry } = fakeCar();
  const camera = new THREE.PerspectiveCamera(35, 16 / 9, 0.1, 200);
  camera.position.set(6, 2.5, 6);
  camera.lookAt(0, 0.5, 0);
  const controls = { target: new THREE.Vector3(0, 0.5, 0) };

  const events = { explodeStart: 0, explodeDone: 0, assembleStart: 0, assembleDone: 0, seated: [] };
  const unsubs = [
    on("explode:start", () => { events.explodeStart++; }),
    on("explode:done", () => { events.explodeDone++; }),
    on("assemble:start", () => { events.assembleStart++; }),
    on("assemble:done", () => { events.assembleDone++; }),
    on("part:seated", (p) => { events.seated.push(p && p.name); }),
  ];

  const exploder = initExplode({ registry, camera, controls });
  const pump = (seconds, step = 0.1) => {
    for (let t = 0; t < seconds; t += step) exploder.update(step);
  };
  return { carRoot, registry, camera, controls, exploder, events, pump, unsubs };
}

test("拆解：事件时序 + shell 静止 + phyllotaxis 落位 + 相机后撤", () => {
  const rig = makeRig();
  const { registry, camera, controls, exploder, events, pump, unsubs } = rig;

  const shell = registry.get("shell").group;
  const shellHome = shell.position.clone();
  const camDist0 = camera.position.distanceTo(controls.target);
  const fov0 = camera.fov;

  assert.equal(exploder.isExploded(), false);
  assert.equal(exploder.explode(), true);
  assert.equal(exploder.isExploded(), true);
  assert.equal(exploder.explode(), false, "重复 explode 应为 no-op");
  assert.equal(events.explodeStart, 1);

  pump(4.0); // 总时长 ~2.6s，留余量

  assert.equal(events.explodeDone, 1, "explode:done 应触发一次");
  assert.ok(shell.position.equals(shellHome), "shell 应保持静止");

  // 其余 19 件全部离开 home，落进 phyllotaxis 槽位
  const moving = [...registry.entries()].filter(([n]) => n !== "shell");
  assert.equal(moving.length, 19);
  moving.forEach(([name, info]) => {
    const p = info.group.position;
    assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z),
      `${name} 位姿不应是 NaN`);

    // 槽位极角/半径（idx 按规范序在非 shell 零件中的序号）
    const idx = [...registry.keys()].filter((n) => n !== "shell").indexOf(name);
    const theta = phyllotaxisAngle(idx);
    const r = phyllotaxisRadius(idx, 1); // dimensions 4.5/2.0 → scale=1
    const horizontal = Math.hypot(p.x, p.z);
    assert.ok(Math.abs(horizontal - r) < 1e-3,
      `${name} 水平半径 ${horizontal.toFixed(3)} 应≈槽位 ${r.toFixed(3)}`);
    const expectX = Math.sin(theta) * r;
    const expectZ = Math.cos(theta) * r;
    assert.ok(Math.abs(p.x - expectX) < 1e-3 && Math.abs(p.z - expectZ) < 1e-3,
      `${name} 应落在黄金角槽位 (${expectX.toFixed(2)}, ${expectZ.toFixed(2)})`);
    assert.ok(p.y > -0.5 && p.y < 1.5, `${name} 槽位高度应在车体附近，实际 ${p.y.toFixed(2)}`);
  });

  // 相机：距离 ×1.35、FOV → 30
  const camDist1 = camera.position.distanceTo(controls.target);
  assert.ok(Math.abs(camDist1 - camDist0 * 1.35) < 1e-6,
    `相机距离 ${camDist1.toFixed(3)} 应≈ ${ (camDist0 * 1.35).toFixed(3) }`);
  assert.ok(Math.abs(camera.fov - 30) < 1e-6, "FOV 应到 30");

  // —— 装回（独立编排） ——
  assert.equal(exploder.assemble(), true);
  assert.equal(events.assembleStart, 1);
  assert.equal(exploder.assemble(), false, "重复 assemble 应为 no-op");

  pump(3.0); // 总时长 ~2.2s

  assert.equal(events.assembleDone, 1, "assemble:done 应触发一次");
  assert.equal(events.seated.length, 19, "19 个运动件各 seated 一次");
  assert.ok(events.seated.every((n) => typeof n === "string" && n !== "shell"));

  for (const [name, info] of registry) {
    const home = HOME[name];
    assert.ok(info.group.position.distanceTo(new THREE.Vector3(...home)) < 1e-6,
      `${name} 应回到 home，实际 ${info.group.position.toArray().map((v) => v.toFixed(3))}`);
    assert.ok(info.group.quaternion.angleTo(new THREE.Quaternion()) < 1e-6,
      `${name} 四元数应回正`);
  }

  // 相机归位
  assert.ok(Math.abs(camera.position.distanceTo(controls.target) - camDist0) < 1e-6);
  assert.ok(Math.abs(camera.fov - fov0) < 1e-6, "FOV 应回到 35");

  for (const u of unsubs) u();
});

test("toggle：拆解 ⇄ 装回状态机", () => {
  const rig = makeRig();
  const { exploder, events, pump, unsubs } = rig;

  assert.equal(exploder.toggle(), true); // → 拆解
  assert.equal(exploder.isExploded(), true);
  pump(4.0);
  assert.equal(events.explodeDone, 1);

  assert.equal(exploder.toggle(), true); // → 装回
  assert.equal(exploder.isExploded(), false);
  pump(3.0);
  assert.equal(events.assembleDone, 1);
  assert.equal(events.seated.length, 19);

  for (const u of unsubs) u();
});
