// tests/phyllotaxis.test.js —— 黄金角布局数学正确性
import test from "node:test";
import assert from "node:assert/strict";
import {
  phyllotaxisAngle,
  phyllotaxisRadius,
  PART_ORDER,
  isStructurePart,
} from "../src/explode.js";

const GOLDEN_DEG = 137.5077640500378;
const GOLDEN_RAD = (GOLDEN_DEG * Math.PI) / 180;
const TAU = Math.PI * 2;

test("phyllotaxisAngle(n) = n × 黄金角（弧度）", () => {
  assert.equal(phyllotaxisAngle(0), 0);
  assert.ok(Math.abs(phyllotaxisAngle(1) - GOLDEN_RAD) < 1e-12);
  assert.ok(Math.abs(phyllotaxisAngle(7) - 7 * GOLDEN_RAD) < 1e-12);
  // 步长与 2π×0.6180339887… 互补（黄金角 ≡ −2π×0.618 mod 2π）
  const step = phyllotaxisAngle(1);
  assert.ok(Math.abs(TAU - step - TAU * 0.6180339887498948) < 1e-9);
});

test("n ≤ 20 极角单调递增且铺满 360°", () => {
  const N = 20;
  const raw = [];
  for (let n = 0; n < N; n++) {
    const a = phyllotaxisAngle(n);
    if (n > 0) assert.ok(a > raw[n - 1], "原始角度应严格递增");
    raw.push(a);
  }

  const norm = raw.map((a) => ((a % TAU) + TAU) % TAU).sort((x, y) => x - y);

  // 相邻间隙（含首尾环绕）均为正，最大间隙 < 2 个均分步长（36°）
  let maxGap = 0;
  for (let i = 0; i < N; i++) {
    const gap = i === N - 1 ? norm[0] + TAU - norm[i] : norm[i + 1] - norm[i];
    assert.ok(gap > 0, "间隙应为正");
    if (gap > maxGap) maxGap = gap;
  }
  assert.ok(maxGap < (TAU / N) * 2, `最大间隙 ${(maxGap * 180) / Math.PI}° 应 < 36°`);

  // 全覆盖：每个 40° 扇区至少落一个点
  for (let s = 0; s < 9; s++) {
    const lo = (s * Math.PI) / 5;
    const hi = ((s + 1) * Math.PI) / 5;
    assert.ok(
      norm.some((a) => a >= lo && a < hi),
      `扇区 [${s * 40}°, ${(s + 1) * 40}°) 应有点`,
    );
  }
});

test("phyllotaxisRadius 单调增长并支持尺寸缩放", () => {
  assert.equal(phyllotaxisRadius(0), 3.2);
  // 3.2 + 0.18 在 IEEE754 下是 3.3800000000000003，浮点用容差比较
  assert.ok(Math.abs(phyllotaxisRadius(1) - 3.38) < 1e-12);
  let prev = -Infinity;
  for (let n = 0; n < 40; n++) {
    const r = phyllotaxisRadius(n);
    assert.ok(r > prev, "半径应随 n 严格递增");
    prev = r;
  }
  assert.ok(Math.abs(phyllotaxisRadius(5, 1.1) - (3.2 + 0.18 * 5) * 1.1) < 1e-12);
});

test("PART_ORDER 恰为合同 20 名且结构件分类正确", () => {
  const EXPECTED = [
    "shell", "hood_front", "door_left", "door_right", "canopy",
    "band_left", "band_right", "wing_rear", "diffuser_rear",
    "wheel_FL", "wheel_FR", "wheel_RL", "wheel_RR",
    "battery_pack", "seat_center", "seat_left", "seat_right",
    "light_front_left", "light_front_right", "light_rear_bar",
  ];
  assert.equal(PART_ORDER.length, 20);
  assert.deepEqual([...PART_ORDER].sort(), [...EXPECTED].sort());

  assert.equal(isStructurePart("battery_pack"), true);
  assert.equal(isStructurePart("wheel_FL"), true);
  assert.equal(isStructurePart("seat_right"), true);
  assert.equal(isStructurePart("shell"), false);
  assert.equal(isStructurePart("door_left"), false);
  assert.equal(isStructurePart("light_rear_bar"), false);
});
