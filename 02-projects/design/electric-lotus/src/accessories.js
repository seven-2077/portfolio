// src/accessories.js —— 配件系统（轮毂 / 尾翼 / 侧裙 / 卡钳热替换）
//
// 用法:
//   const acc = initAccessories({ registry });
//   acc.setGroup("wheel", "turbine");   // 变体即时换装，emit accessory:changed
//   acc.getActive();                    // { wheel, wing, skirts, caliper }（供配置导出）
//
// 设计要点:
//   - 变体几何全部程序化生成（three 纯几何，Node 可导入；无 DOM 依赖）
//   - 轮毂: forged(5 组双辐) / turbine(封闭气动盘 + 斜向径向槽) / petal(6 瓣莲花镂空辐)
//     —— 装进每个 wheel_XX 的 "rim" Group，原辐条以 userData.isRimVariant 标记隐藏
//   - 尾翼: gt(大尾板 + 2 端板 + 支柱) / ducktail(短唇)，只动 wing_rear 的子节点，
//     不碰零件自身的 home pivot（拆解编排不受影响）
//   - 侧裙: 沿门槛的侧刃盒，挂到 shell 下方，visible 开关
//   - 卡钳: 找 wheel_XX 内 subRole='caliper' 的网格改色，缺失则生成 4 个卡钳弧
//     （red 0xd23c2e / gold 0xd9a521 / black 0x1a1a1c）
//
// deps.THREE 允许注入（签名兼容），本模块默认用自带的 three 导入。

import * as THREE from "three";
import { emit } from "./events.js";

export const ACCESSORY_DEFAULTS = { wheel: "forged", wing: "gt", skirts: "off", caliper: "red" };

export const ACCESSORY_VALUES = {
  wheel: ["forged", "turbine", "petal"],
  wing: ["gt", "ducktail"],
  skirts: ["on", "off"],
  caliper: ["red", "gold", "black"],
};

export const CALIPER_COLORS = { red: 0xd23c2e, gold: 0xd9a521, black: 0x1a1a1c };

const RIM_RADIUS = 0.34; // 轮辋半径（米）
const RIM_WIDTH = 0.26;  // 轮辋宽（米）

export function initAccessories({ registry } = {}) {
  const map = registry instanceof Map ? registry : new Map();

  const active = { ...ACCESSORY_DEFAULTS };

  // ---- 共享资源（惰性构建，缓存复用） ----
  const templates = new Map();      // "rim:forged" → Group 模板（clone 共享几何）
  let rimMat = null;
  let wingMat = null;
  let skirtMat = null;
  let caliperMat = null;

  function getRimMat() {
    if (!rimMat) {
      rimMat = new THREE.MeshStandardMaterial({
        color: 0xb4b9c0, metalness: 0.9, roughness: 0.3,
        emissive: 0x0c0d10, emissiveIntensity: 1,
      });
    }
    return rimMat;
  }
  function getWingMat() {
    if (!wingMat) {
      wingMat = new THREE.MeshStandardMaterial({
        color: 0x2b2f36, metalness: 0.75, roughness: 0.4,
        emissive: 0x0a0b0d, emissiveIntensity: 1,
      });
    }
    return wingMat;
  }
  function getSkirtMat() {
    if (!skirtMat) {
      skirtMat = new THREE.MeshStandardMaterial({
        color: 0x17181c, metalness: 0.6, roughness: 0.5,
      });
    }
    return skirtMat;
  }
  function getCaliperMat() {
    if (!caliperMat) {
      caliperMat = new THREE.MeshStandardMaterial({
        color: CALIPER_COLORS.red, metalness: 0.55, roughness: 0.35,
        emissive: 0x090909, emissiveIntensity: 1,
      });
    }
    return caliperMat;
  }

  // ------------------------------------------------------------ 工具

  /** 零件在自身局部空间的几何包围盒（相对某祖先） */
  function localBox(obj, relativeTo) {
    relativeTo.updateWorldMatrix(true, false);
    obj.updateWorldMatrix(true, false);
    const inv = new THREE.Matrix4().copy(relativeTo.matrixWorld).invert();
    const box = new THREE.Box3().makeEmpty();
    const m = new THREE.Matrix4();
    obj.traverse((o) => {
      if (!o.isMesh || !o.geometry) return;
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      m.multiplyMatrices(inv, o.matrixWorld);
      box.union(o.geometry.boundingBox.clone().applyMatrix4(m));
    });
    return box;
  }

  function unitAxis(i) {
    return i === 0 ? new THREE.Vector3(1, 0, 0)
      : i === 1 ? new THREE.Vector3(0, 1, 0)
      : new THREE.Vector3(0, 0, 1);
  }

  function wheelEntries() {
    const out = [];
    for (const [name, info] of map) {
      if (name.startsWith("wheel_") && info && info.group) out.push({ name, group: info.group });
    }
    return out;
  }

  function findRim(wheelGroup) {
    let rim = null;
    wheelGroup.traverse((o) => {
      if (!rim && o.isGroup && (o.userData.subRole === "rim" || o.name === "rim")) rim = o;
    });
    return rim;
  }

  /** 从轮胎/轮辐包围盒推断车轴方向（轮组局部空间）→ 轮毂变体的对齐四元数 + 中心 */
  function axleFrame(rim) {
    const box = localBox(rim, rim);
    if (box.isEmpty()) {
      return { quat: new THREE.Quaternion(), center: new THREE.Vector3() };
    }
    const size = box.getSize(new THREE.Vector3());
    let minI = 0;
    if (size.y < size.x && size.y <= size.z) minI = 1;
    else if (size.z < size.x && size.z <= size.y) minI = 2;
    const axis = unitAxis(minI);
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), axis);
    return { quat, center: box.getCenter(new THREE.Vector3()), size };
  }

  // ------------------------------------------------------------ 轮毂变体模板

  function buildRimTemplate(kind) {
    const key = `rim:${kind}`;
    if (templates.has(key)) return templates.get(key);

    const g = new THREE.Group();
    const mat = getRimMat();
    const R = RIM_RADIUS;

    // 外圈轮辋 + 中心毂（三种款式共用骨架）
    const ring = new THREE.Mesh(new THREE.TorusGeometry(R - 0.03, 0.032, 10, 48), mat);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, RIM_WIDTH * 0.55, 20), mat);
    hub.rotation.x = Math.PI / 2; // 圆柱默认沿 Y，转到 Z 轴（车轴）
    g.add(ring, hub);

    if (kind === "forged") {
      // 5 组双辐（10 根细辐条）
      for (let i = 0; i < 5; i++) {
        const base = (i * Math.PI * 2) / 5;
        for (const off of [-0.085, 0.085]) {
          const spoke = new THREE.Mesh(new THREE.BoxGeometry(R - 0.1, 0.034, 0.05), mat);
          const a = base + off;
          spoke.position.set(Math.cos(a) * (R / 2 - 0.02), Math.sin(a) * (R / 2 - 0.02), 0);
          spoke.rotation.z = a;
          g.add(spoke);
        }
      }
    } else if (kind === "turbine") {
      // 封闭气动盘 + 斜向径向槽（盘面 + 拨风叶片）
      const disc = new THREE.Mesh(new THREE.CylinderGeometry(R - 0.035, R - 0.03, 0.04, 48), mat);
      disc.rotation.x = Math.PI / 2;
      g.add(disc);
      for (let i = 0; i < 12; i++) {
        const blade = new THREE.Mesh(new THREE.BoxGeometry(R - 0.12, 0.05, 0.016), mat);
        const a = (i * Math.PI * 2) / 12;
        const holder = new THREE.Group();
        holder.rotation.z = a;
        blade.position.x = (R - 0.12) / 2 + 0.05;
        blade.rotation.x = 0.62; // 斜切角 → 斜向径向槽的视觉
        holder.add(blade);
        g.add(holder);
      }
    } else if (kind === "petal") {
      // 6 瓣莲花镂空辐（叶片形挤出）
      const shape = new THREE.Shape();
      shape.moveTo(0.05, -0.042);
      shape.quadraticCurveTo(0.19, -0.075, R - 0.05, -0.02);
      shape.quadraticCurveTo(R - 0.02, 0, R - 0.05, 0.02);
      shape.quadraticCurveTo(0.19, 0.075, 0.05, 0.042);
      shape.closePath();
      const petalGeo = new THREE.ExtrudeGeometry(shape, {
        depth: 0.045, bevelEnabled: true, bevelSize: 0.006, bevelThickness: 0.006, bevelSegments: 2,
      });
      petalGeo.translate(0, 0, -0.0225);
      for (let i = 0; i < 6; i++) {
        const petal = new THREE.Mesh(petalGeo, mat);
        petal.rotation.z = (i * Math.PI * 2) / 6;
        g.add(petal);
      }
    }

    g.userData.variantKind = kind;
    templates.set(key, g);
    return g;
  }

  function applyWheel(kind) {
    for (const { name, group } of wheelEntries()) {
      const rim = findRim(group);
      if (!rim) continue;

      // 移除旧变体，隐藏原辐条
      for (let i = rim.children.length - 1; i >= 0; i--) {
        const child = rim.children[i];
        if (child.userData.isRimVariant) rim.remove(child);
      }
      for (const child of rim.children) {
        if (!child.userData.isRimVariant) {
          child.visible = false;
          child.userData.origHiddenByAccessory = true;
        }
      }

      const frame = axleFrame(rim);
      const variant = buildRimTemplate(kind).clone();
      variant.userData.isRimVariant = true;
      variant.userData.partName = name;
      variant.userData.variantKind = kind;
      variant.quaternion.copy(frame.quat);
      variant.position.copy(frame.center);
      variant.traverse((o) => { if (o.isMesh) o.userData.partName = name; });
      rim.add(variant);
    }
  }

  // ------------------------------------------------------------ 尾翼变体

  function buildWingTemplate(kind) {
    const key = `wing:${kind}`;
    if (templates.has(key)) return templates.get(key);

    const g = new THREE.Group();
    const mat = getWingMat();

    if (kind === "gt") {
      // 大尾板 + 2 端板 + 2 支柱（X=翼展, Y=厚度向, Z=弦向）
      const span = 1.3, chord = 0.3;
      const plane = new THREE.Mesh(new THREE.BoxGeometry(span, 0.028, chord * 0.9), mat);
      plane.position.y = 0.075;
      g.add(plane);
      for (const sx of [-1, 1]) {
        const plate = new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.15, chord * 0.85), mat);
        plate.position.set((sx * span) / 2, 0.075, 0);
        g.add(plate);
        const strut = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.15, 0.05), mat);
        strut.position.set(sx * span * 0.3, 0.005, 0);
        g.add(strut);
      }
    } else {
      // ducktail 短唇
      const lip = new THREE.Mesh(new THREE.BoxGeometry(1.26, 0.035, 0.14), mat);
      lip.position.set(0, 0.03, -0.07);
      lip.rotation.x = -0.18;
      g.add(lip);
    }

    g.userData.variantKind = kind;
    templates.set(key, g);
    return g;
  }

  function applyWing(kind) {
    const info = map.get("wing_rear");
    const wing = info && info.group;
    if (!wing) return;

    for (let i = wing.children.length - 1; i >= 0; i--) {
      const child = wing.children[i];
      if (child.userData.isWingVariant) wing.remove(child);
    }
    for (const child of wing.children) {
      if (!child.userData.isWingVariant) {
        child.visible = false;
        child.userData.origHiddenByAccessory = true;
      }
    }

    const box = localBox(wing, wing);
    let quat = new THREE.Quaternion();
    let center = new THREE.Vector3();
    let size = new THREE.Vector3(1.3, 0.1, 0.3);
    if (!box.isEmpty()) {
      size = box.getSize(new THREE.Vector3());
      center = box.getCenter(new THREE.Vector3());
      // 最长轴=翼展, 最薄轴=厚度向, 余下=弦向；第三轴由叉乘保证右手系
      const axes = [0, 1, 2].sort((a, b) => size[b] - size[a]); // [max, mid, min]
      const spanDir = unitAxis(axes[0]);
      const thickDir = unitAxis(axes[2]);
      const chordDir = new THREE.Vector3().crossVectors(spanDir, thickDir).normalize();
      const basis = new THREE.Matrix4().makeBasis(spanDir, thickDir, chordDir);
      quat.setFromRotationMatrix(basis);
    }

    const variant = buildWingTemplate(kind).clone();
    variant.userData.isWingVariant = true;
    variant.userData.variantKind = kind;
    // 模板按名义尺寸（展 1.3 × 弦 0.3）建，按原翼实测尺寸缩放贴合
    // 变体局部轴: X=翼展, Z=弦向（见 buildWingTemplate）
    const order = [0, 1, 2].sort((a, b) => size[b] - size[a]);
    const spanLen = size[order[0]] || 1.3;
    const chordLen = size[order[1]] || 0.3;
    variant.scale.set(spanLen / 1.3, 1, chordLen / 0.3);
    variant.quaternion.copy(quat);
    variant.position.copy(center);
    variant.traverse((o) => { if (o.isMesh) o.userData.partName = "wing_rear"; });
    wing.add(variant);
  }

  // ------------------------------------------------------------ 侧裙

  function applySkirts(value) {
    const info = map.get("shell");
    const shell = info && info.group;
    if (!shell) return;

    // 单 holder（isSkirtHolder）承载左右两片侧刃；已存在则只切可见性
    let holder = shell.children.find((c) => c.userData.isSkirtHolder);

    if (!holder && value === "on") {
      const box = localBox(shell, shell);
      if (box.isEmpty()) return;
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      // 最长轴=车长, 最薄轴=上向, 余下=横向
      const order = [0, 1, 2].sort((a, b) => size[b] - size[a]);
      const longDir = unitAxis(order[0]);
      const upDir = unitAxis(order[2]);
      const latDir = new THREE.Vector3().crossVectors(longDir, upDir).normalize();
      const basis = new THREE.Matrix4().makeBasis(longDir, upDir, latDir);
      const quat = new THREE.Quaternion().setFromRotationMatrix(basis);

      const longLen = size[order[0]] * 0.72;
      const halfLat = size[order[1]] / 2;
      const halfUp = size[order[2]] / 2;

      holder = new THREE.Group();
      holder.userData.isSkirtHolder = true;
      holder.userData.isSkirt = true;
      holder.userData.partName = "shell";
      holder.quaternion.copy(quat);
      holder.position.copy(center);

      for (const side of [-1, 1]) {
        const blade = new THREE.Mesh(
          new THREE.BoxGeometry(longLen, 0.05, 0.12),
          getSkirtMat(),
        );
        blade.userData.isSkirt = true;
        blade.userData.partName = "shell";
        // holder 局部系：X→车长, Y→上, Z→横向
        blade.position.set(0, -halfUp + 0.05, side * (halfLat - 0.01));
        holder.add(blade);
      }
      shell.add(holder);
    }

    shell.traverse((o) => { if (o.userData.isSkirt) o.visible = value === "on"; });
  }

  // ------------------------------------------------------------ 卡钳

  function applyCaliper(value) {
    const hex = CALIPER_COLORS[value];
    if (hex === undefined) return;

    for (const { name, group } of wheelEntries()) {
      let calipers = [];
      group.traverse((o) => {
        if (o.isMesh && o.userData.subRole === "caliper") calipers.push(o);
      });

      if (calipers.length === 0) {
        // 缺失 → 生成一个卡钳弧（贴在刹车盘外缘）
        const rim = findRim(group);
        const frame = rim ? axleFrame(rim) : { quat: new THREE.Quaternion(), center: new THREE.Vector3() };
        const arc = new THREE.Mesh(
          new THREE.TorusGeometry(RIM_RADIUS * 0.55, 0.03, 6, 12, 1.5),
          getCaliperMat(),
        );
        const holder = new THREE.Group();
        holder.userData.partName = name;
        holder.userData.subRole = "caliper";
        holder.quaternion.copy(frame.quat);
        holder.position.copy(frame.center);
        // 绕车轴转到后上方位置
        holder.rotateZ(2.1);
        holder.add(arc);
        arc.userData.partName = name;
        arc.userData.subRole = "caliper";
        group.add(holder);
        calipers = [arc];
      }

      for (const mesh of calipers) {
        let mat = mesh.material;
        // 防御：若材质被 applyRoles 等换成共享实例，先克隆再改色，
        // 避免把共享车漆/金属材质整体染成卡钳色
        if (mat && mat.color && mesh.userData._calMatOwned !== true) {
          mat = mat.clone();
          mesh.material = mat;
          mesh.userData._calMatOwned = true;
        }
        if (mat && mat.color) mat.color.setHex(hex);
        if (mat && mat.emissive && value === "gold") mat.emissive.setHex(0x141005);
        else if (mat && mat.emissive) mat.emissive.setHex(0x090909);
      }
    }
  }

  // ------------------------------------------------------------ 公共 API

  function setGroup(group, value) {
    if (!Object.prototype.hasOwnProperty.call(ACCESSORY_VALUES, group)) return false;
    if (!ACCESSORY_VALUES[group].includes(value)) return false;
    if (active[group] === value) return true; // 幂等：值未变不重复施工、不重复发事件

    active[group] = value;
    switch (group) {
      case "wheel": applyWheel(value); break;
      case "wing": applyWing(value); break;
      case "skirts": applySkirts(value); break;
      case "caliper": applyCaliper(value); break;
      default: break;
    }
    emit("accessory:changed", { group, value });
    return true;
  }

  function getActive() {
    return { ...active };
  }

  // 初始即落到默认款式（静默，不发事件；面板随后 setGroup 同值为幂等 no-op）
  applyWheel(active.wheel);
  applyWing(active.wing);
  applySkirts(active.skirts);
  applyCaliper(active.caliper);

  return { setGroup, getActive };
}
