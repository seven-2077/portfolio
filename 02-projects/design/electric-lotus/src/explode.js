// src/explode.js —— 拆解编排（机械式「开花」，非爆裂）
//
// 设计要点:
//   1. 每个零件在 init 时抓取「家」快照（carRoot 局部空间位姿），与 build 顺序无关。
//   2. 轨迹两段式: 0-45% 走机构动作（铰链/鸥翼/滑轨/旋转…），45-100% 滑翔到
//      phyllotaxis（黄金角 137.5077640500378°）花瓣槽位 —— 俯视呈一朵机械莲花。
//   3. 时序: battery 先行（慢速 power2Out 1.6s）→ 车轮/座椅 → 面板最后
//      （backOut(1.4) 过冲咔哒感），零件间 0.06s 错峰，总长 ~2.6s。
//   4. 装回是独立编排（非简单倒放）: 面板带过冲先归位并逐个 emit part:seated，
//      结构件随后沉降，总长 ~2.2s。
//   5. 相机: 沿当前视线后撤 ×1.35、FOV 35→30（power2InOut ~2s），装回时反向归位；
//      controls.target 不动，转台继续转（所有位姿都在 carRoot 局部空间计算）。
//
// 用法:
//   const exploder = initExplode({ registry, camera, controls });
//   exploder.update(deltaSeconds);   // 渲染循环每帧调用
//   exploder.toggle();

import * as THREE from "three";
import { emit } from "./events.js";
import { TweenManager, power2Out, power2InOut, sineInOut, backOut } from "./tween.js";

const GOLDEN_ANGLE_DEG = 137.5077640500378;

/** 黄金角（弧度）：第 n 个零件的极角 = phyllotaxisAngle(n) */
export function phyllotaxisAngle(n) {
  return (n * GOLDEN_ANGLE_DEG * Math.PI) / 180;
}

/** phyllotaxis 槽位半径（米）：3.2 + 0.18n，乘以车身尺寸缩放 */
export function phyllotaxisRadius(n, scale = 1) {
  return (3.2 + 0.18 * n) * scale;
}

/** 合同中的 20 个零件名（规范顺序，决定错峰与花瓣编号） */
export const PART_ORDER = [
  "shell", "hood_front", "door_left", "door_right", "canopy",
  "band_left", "band_right", "wing_rear", "diffuser_rear",
  "wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR",
  "battery_pack", "seat_center", "seat_left", "seat_right",
  "light_front_left", "light_front_right", "light_rear_bar",
];

/** 结构件（先动/后归位）: 电池 + 四轮 + 三席；其余（除 shell）都按面板处理 */
export function isStructurePart(name) {
  return name === "battery_pack" || name.startsWith("wheel_") || name.startsWith("seat_");
}

const DEG = Math.PI / 180;

export function initExplode({ registry, camera, controls } = {}) {
  const mgr = new TweenManager();
  const state = { exploded: false, busy: null };

  // ---- 临时对象（闭包内共享，避免每帧分配） ----
  const _v = new THREE.Vector3();
  const _p = new THREE.Vector3();
  const _q = new THREE.Quaternion();
  const _s = new THREE.Vector3();
  const _m = new THREE.Matrix4();
  const _invCar = new THREE.Matrix4();
  const _invP = new THREE.Matrix4();
  const _qCar = new THREE.Quaternion();
  const _qPar = new THREE.Quaternion();
  const _qa = new THREE.Quaternion();
  const _qs = new THREE.Quaternion();
  const _pa = new THREE.Vector3();

  // ---- 发现 carRoot（带 userData.dimensions 的祖先） ----
  let carRoot = null;
  if (registry && registry.size > 0) {
    for (const info of registry.values()) {
      if (info && info.group) {
        let r = info.group;
        while (r.parent && !(r.userData && r.userData.dimensions)) r = r.parent;
        carRoot = r;
        break;
      }
    }
  }

  const parts = [];
  let camHome = null; // { rel: Vector3, fov: number } —— 装回时的相机归位目标
  let needsMatrixPath = false;

  if (carRoot) {
    carRoot.updateWorldMatrix(true, false);
    _invCar.copy(carRoot.matrixWorld).invert();

    // ---- 推导车体轴（车空间）: L=横向(指向右侧), F=前向, U=上 ----
    const posOf = (name) => {
      const info = registry.get(name);
      if (!info || !info.group) return null;
      info.group.updateWorldMatrix(true, false);
      return _v.setFromMatrixPosition(info.group.matrixWorld).applyMatrix4(_invCar).clone();
    };

    let L = null;
    for (const [a, b] of [
      ["door_right", "door_left"],
      ["wheel_FR", "wheel_FL"],
      ["band_right", "band_left"],
    ]) {
      const pa = posOf(a), pb = posOf(b);
      if (pa && pb) {
        const d = pa.sub(pb);
        if (d.lengthSq() > 1e-6) { L = d.normalize(); break; }
      }
    }
    if (!L) L = new THREE.Vector3(1, 0, 0);

    let F = null;
    for (const [a, b] of [
      ["hood_front", "wing_rear"],
      ["light_front_left", "light_rear_bar"],
    ]) {
      const pa = posOf(a), pb = posOf(b);
      if (pa && pb) {
        const d = pa.sub(pb);
        if (d.lengthSq() > 1e-6) { F = d.normalize(); break; }
      }
    }
    if (!F) F = new THREE.Vector3(0, 0, 1);

    // U = 世界上方（车空间）；F、L 投影到水平面 → 三轴正交，槽位严格落在水平面
    const U = new THREE.Vector3(0, 1, 0).transformDirection(_invCar);
    F.addScaledVector(U, -F.dot(U));
    if (F.lengthSq() < 1e-6) F.crossVectors(L, U); // F 几乎竖直时的兜底
    if (F.lengthSq() < 1e-6) F.set(0, 0, 1);
    F.normalize();
    L.addScaledVector(U, -L.dot(U));
    if (L.lengthSq() < 1e-6) L.crossVectors(U, F);
    L.normalize();
    // 水平面内再保证 F ⊥ L
    F.addScaledVector(L, -F.dot(L));
    if (F.lengthSq() < 1e-6) F.crossVectors(L, U);
    F.normalize();
    // 右手系校验: F×L 应指向上（合同零件布局下恒真；兜底翻 L 保住多数横向件）
    if (new THREE.Vector3().crossVectors(F, L).dot(U) < 0) L.negate();

    // ---- 尺寸缩放 ----
    const dims = carRoot.userData && carRoot.userData.dimensions;
    const scale = dims && dims.length
      ? (dims.length / 4.5 + (dims.width || 2.0) / 2.0) / 2
      : 1;

    // ---- 采集运动零件（shell 静止跳过），保持 PART_ORDER 规范序 ----
    const names = PART_ORDER.filter((n) => n !== "shell" && registry.has(n));
    for (const name of registry.keys()) {
      if (name !== "shell" && !names.includes(name)) names.push(name); // 合同外零件兜底
    }

    names.forEach((name, idx) => {
      const info = registry.get(name);
      if (!info || !info.group) return;
      const rec = makeRecord(name, info, idx);
      if (rec) parts.push(rec);
    });

    // ---- 时序编排（拆解） ----
    const batteries = parts.filter((p) => p.name === "battery_pack");
    const rolls = parts.filter((p) => p.name.startsWith("wheel_") || p.name.startsWith("seat_"));
    const panels = parts.filter((p) => !isStructurePart(p.name));

    batteries.forEach((p) => { p.delay = 0; p.duration = 1.6; p.easeMech = power2Out; p.easeGlide = power2Out; });
    rolls.forEach((p, i) => { p.delay = 0.18 + 0.06 * i; p.duration = 1.5; p.easeMech = power2Out; p.easeGlide = power2Out; });
    panels.forEach((p, i) => { p.delay = 0.6 + 0.06 * i; p.duration = 1.4; p.easeMech = backOut(1.4); p.easeGlide = sineInOut; });

    needsMatrixPath = parts.some((p) => !p.parentIsCar);

    function makeRecord(name, info, idx) {
      const group = info.group;
      group.updateWorldMatrix(true, false);
      _m.multiplyMatrices(_invCar, group.matrixWorld).decompose(_p, _q, _s);
      const homePos = _p.clone();
      const homeQuat = _q.clone();

      const type = (info.explode && info.explode.type) || null;
      const side = homePos.dot(L) >= 0 ? 1 : -1;

      const move = new THREE.Vector3();
      let axis = null, angle = 0;
      let spinAxis = null, spinAngle = 0;

      switch (type) {
        case "hinge_up": // 前盖绕后铰链上翻 ~75°
          axis = L.clone(); angle = -75 * DEG;
          break;
        case "gullwing": // 鸥翼门绕车顶导轨铰链上扬 ~60°（外侧朝上）
          axis = F.clone(); angle = side * 60 * DEG;
          move.copy(F).multiplyScalar(0.08);
          break;
        case "lift_tilt": // 座舱罩升起 + 后仰
          axis = L.clone(); angle = -25 * DEG;
          move.copy(U).multiplyScalar(0.55);
          break;
        case "slide_lateral": // 技术腰线横向滑出
          move.copy(L).multiplyScalar(side * 0.75);
          break;
        case "lift_back": // 尾翼抬起 + 后移
          move.copy(U).multiplyScalar(0.35).addScaledVector(F, -0.55);
          break;
        case "slide_back": // 扩散器 / 尾灯带后滑
          move.copy(F).multiplyScalar(name === "diffuser_rear" ? -0.9 : -0.7);
          break;
        case "slide_forward": // 前灯前推
          move.copy(F).multiplyScalar(0.6);
          break;
        case "spin_out": // 车轮沿车轴滑出 + 自旋 720°
          move.copy(L).multiplyScalar(side * 0.85);
          spinAxis = L.clone();
          spinAngle = side * 720 * DEG;
          break;
        case "drop_down": // 电池组沉入地板下
          move.copy(U).multiplyScalar(-0.75);
          break;
        case "rail_up": // 座椅沿滑轨升起
          move.copy(U).multiplyScalar(0.5);
          break;
        default: // 未知类型：向上浮起兜底
          move.copy(U).multiplyScalar(0.5);
      }

      const mechPos = homePos.clone().add(move);
      const mechQuat = homeQuat.clone();
      if (axis && angle !== 0) {
        mechQuat.premultiply(new THREE.Quaternion().setFromAxisAngle(axis, angle));
      }

      // ---- phyllotaxis 花瓣槽位（车空间, L/F 平面） ----
      const theta = phyllotaxisAngle(idx);
      const r = phyllotaxisRadius(idx, scale);
      const slotPos = new THREE.Vector3()
        .addScaledVector(L, Math.sin(theta) * r)
        .addScaledVector(F, Math.cos(theta) * r)
        .addScaledVector(U, 0.3 + 0.25 * Math.sin(idx * 2.0));
      // 展示姿态：绕上轴轻微自转（交替方向），俯视时花瓣各自展开
      const tilt = (idx % 2 === 0 ? 1 : -1) * 0.34;
      const slotQuat = new THREE.Quaternion().setFromAxisAngle(U, tilt).multiply(homeQuat);

      return {
        name, info, group, idx, type, side,
        parentIsCar: group.parent === carRoot,
        homePos, homeQuat, mechPos, mechQuat, slotPos, slotQuat,
        spinAxis, spinAngle,
        delay: 0, duration: 1,
        easeMech: power2Out, easeGlide: power2InOut,
      };
    }
  }

  // ---- 位姿写入（carRoot 局部空间 → 零件父空间） ----
  function applyPose(rec, pos, quat) {
    const g = rec.group;
    if (rec.parentIsCar) {
      g.position.copy(pos);
      g.quaternion.copy(quat);
      return;
    }
    const parent = g.parent;
    _invP.copy(parent.matrixWorld).invert();
    _p.copy(pos).applyMatrix4(carRoot.matrixWorld).applyMatrix4(_invP);
    g.position.copy(_p);
    _qCar.setFromRotationMatrix(carRoot.matrixWorld);
    _qPar.setFromRotationMatrix(parent.matrixWorld).invert();
    g.quaternion.copy(_qPar).multiply(_qCar).multiply(quat);
  }

  // ---- 抓取零件当前 carRoot 局部空间位姿（转台旋转下依然正确） ----
  function capture(rec) {
    carRoot.updateWorldMatrix(true, false);
    rec.group.updateWorldMatrix(true, false);
    _invCar.copy(carRoot.matrixWorld).invert();
    _m.multiplyMatrices(_invCar, rec.group.matrixWorld).decompose(_p, _q, _s);
    return { pos: _p.clone(), quat: _q.clone() };
  }

  // ---- 相机编排 ----
  function startCameraTween(dir) {
    if (!camera || !controls || !controls.target) return;
    const target = controls.target.clone();

    if (dir === "back") {
      const fromRel = camera.position.clone().sub(target);
      const fov0 = camera.fov;
      mgr.add({
        from: 0, to: 1, duration: 2.0, ease: power2InOut, tag: "explode",
        onUpdate: (v) => {
          camera.position.copy(target).addScaledVector(fromRel, 1 + 0.35 * v);
          camera.fov = fov0 + (30 - fov0) * v;
          camera.updateProjectionMatrix();
        },
      });
    } else if (dir === "home" && camHome) {
      const fromRel = camera.position.clone().sub(target);
      const fov0 = camera.fov;
      mgr.add({
        from: 0, to: 1, duration: 1.8, ease: power2InOut, tag: "assemble",
        onUpdate: (v) => {
          _pa.copy(fromRel).lerp(camHome.rel, v);
          camera.position.copy(target).add(_pa);
          camera.fov = fov0 + (camHome.fov - fov0) * v;
          camera.updateProjectionMatrix();
        },
      });
    }
  }

  // ---- 拆解 ----
  function explode() {
    if (state.exploded && state.busy !== "assemble") return false;
    const interrupting = state.busy === "assemble";

    mgr.cancelTag("assemble");
    mgr.cancelTag("explode");
    state.exploded = true;
    state.busy = "explode";

    // 相机后撤起点：若正从装回途中打断，保留原 camHome，只从当前位置继续后撤
    if (!interrupting && camera && controls && controls.target) {
      camHome = {
        rel: camera.position.clone().sub(controls.target.clone()),
        fov: camera.fov,
      };
    }
    startCameraTween("back");
    emit("explode:start", { exploded: true });

    for (const rec of parts) {
      const from = capture(rec);

      // 阶段 A: 机构动作（0 → 45% 时长）
      mgr.add({
        delay: rec.delay,
        duration: rec.duration * 0.45,
        ease: rec.easeMech,
        tag: "explode",
        onUpdate: (v) => {
          _pa.copy(from.pos).lerp(rec.mechPos, v);
          _qa.copy(from.quat).slerp(rec.mechQuat, v);
          if (rec.spinAngle) {
            _qs.setFromAxisAngle(rec.spinAxis, rec.spinAngle * v);
            _qa.premultiply(_qs);
          }
          applyPose(rec, _pa, _qa);
        },
      });

      // 阶段 B: 滑翔到 phyllotaxis 槽位（45% → 100%）
      mgr.add({
        delay: rec.delay + rec.duration * 0.45,
        duration: rec.duration * 0.55,
        ease: rec.easeGlide,
        tag: "explode",
        onUpdate: (v) => {
          _pa.copy(rec.mechPos).lerp(rec.slotPos, v);
          _qa.copy(rec.mechQuat).slerp(rec.slotQuat, v);
          applyPose(rec, _pa, _qa);
        },
      });
    }

    const total = parts.reduce((m, p) => Math.max(m, p.delay + p.duration), 0) || 0.1;
    mgr.add({
      delay: total + 0.02, duration: 0.01, tag: "explode",
      onComplete: () => {
        if (state.busy === "explode") {
          state.busy = null;
          emit("explode:done", { exploded: true });
        }
      },
    });
    return true;
  }

  // ---- 装回（独立编排：面板带过冲先归位 → 结构件沉降） ----
  function scheduleSeat(rec, delay, duration, ease) {
    const from = capture(rec);
    mgr.add({
      delay, duration, ease, tag: "assemble",
      onUpdate: (v) => {
        _pa.copy(from.pos).lerp(rec.homePos, v);
        _qa.copy(from.quat).slerp(rec.homeQuat, v);
        applyPose(rec, _pa, _qa);
      },
      onComplete: () => emit("part:seated", { name: rec.name }),
    });
  }

  function assemble() {
    if (!state.exploded && state.busy !== "explode") return false;

    mgr.cancelTag("explode");
    mgr.cancelTag("assemble");
    state.exploded = false;
    state.busy = "assemble";

    startCameraTween("home");
    emit("assemble:start", { exploded: false });

    const panels = parts.filter((p) => !isStructurePart(p.name));
    const rolls = parts.filter((p) => isStructurePart(p.name) && p.name !== "battery_pack");
    const batteries = parts.filter((p) => p.name === "battery_pack");

    // 面板先咔哒归位（过冲），逐个 seated
    panels.forEach((rec, i) => scheduleSeat(rec, 0.05 * i, 1.0, backOut(1.4)));
    // 电池（结构）随后慢沉
    batteries.forEach((rec) => scheduleSeat(rec, 0.6, 1.4, power2Out));
    // 车轮 / 座椅最后落位
    rolls.forEach((rec, i) => scheduleSeat(rec, 0.65 + 0.05 * i, 1.2, power2Out));

    const lastPanel = panels.length ? 0.05 * (panels.length - 1) + 1.0 : 0;
    const lastRoll = rolls.length ? 0.65 + 0.05 * (rolls.length - 1) + 1.2 : 0;
    const lastBatt = batteries.length ? 0.6 + 1.4 : 0;
    const endAt = Math.max(lastPanel, lastRoll, lastBatt) + 0.05;

    mgr.add({
      delay: endAt, duration: 0.01, tag: "assemble",
      onComplete: () => {
        if (state.busy === "assemble") {
          state.busy = null;
          emit("assemble:done", { exploded: false });
        }
      },
    });
    return true;
  }

  function toggle() {
    return state.exploded ? assemble() : explode();
  }

  function isExploded() {
    return state.exploded;
  }

  /** 每帧调用：推进补间（含相机）；嵌套父节点路径时先刷新世界矩阵 */
  function update(deltaSeconds) {
    if (needsMatrixPath && state.busy && carRoot) {
      carRoot.updateWorldMatrix(true, true);
    }
    mgr.update(deltaSeconds || 0);
  }

  function dispose() {
    mgr.clear();
    state.exploded = false;
    state.busy = null;
  }

  return { explode, assemble, toggle, isExploded, update, dispose };
}
