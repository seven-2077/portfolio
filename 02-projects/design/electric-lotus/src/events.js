// 极简事件总线 —— 模块间解耦通路（拆解/音频、拾取/HUD 等）
// 用法: import { on, off, emit } from "./events.js";
//
// 事件契约:
//   explode:start / explode:done   { exploded: true }
//   assemble:start / assemble:done { exploded: false }
//   part:seated   { name }   零件咔哒入位（音效）
//   part:pick     { name }   拾取结果变化
//   preset:before { name }   相机机位切换
//   background:switch { name } 背景切换
//   paint:changed { params } 喷漆参数变化
//   accessory:changed { group, value } 配件变化
//   audio:tick    { action } 通用 UI 点击

const listeners = new Map();

export function on(type, fn) {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type).add(fn);
  return () => off(type, fn);
}

export function off(type, fn) {
  const set = listeners.get(type);
  if (set) set.delete(fn);
}

export function emit(type, payload) {
  const set = listeners.get(type);
  if (!set) return;
  for (const fn of [...set]) {
    try {
      fn(payload);
    } catch (err) {
      console.error("[events] listener threw:", type, err);
    }
  }
}