// src/tween.js —— 极简确定性补间内核（零依赖，Node / 浏览器通用）
//
// 用法:
//   const mgr = createTweenManager();
//   mgr.add({ from: 0, to: 1, duration: 0.5, delay: 0.1,
//             ease: power2Out, onUpdate(v, e, p) {}, onComplete(v) {} });
//   mgr.update(deltaSeconds);        // 每帧推进（渲染循环里调用）
//   mgr.update(absoluteTime, true);  // 可选：绝对时间模式
//
// 约定:
//   - 全部以「秒」为单位；ease 接收 0..1 返回缓动值（backOut 允许越过 1 形成过冲）
//   - update 内部推进，绝不使用 setInterval / CSS 动画
//   - add() 返回 { cancel() }；cancelTag(tag) 批量取消（拆解/装回切换用）

export const linear = (t) => t;

export const power2Out = (t) => 1 - (1 - t) * (1 - t);

export const power3Out = (t) => 1 - Math.pow(1 - t, 3);

export const power2InOut = (t) =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

export const sineInOut = (t) => -(Math.cos(Math.PI * t) - 1) / 2;

// backOut(overshoot) → 返回带回弹过冲的缓动函数
// 默认 1.70158 为经典 back 过冲量；拆解面板用 backOut(1.4)（更克制的机械咔哒感）
export function backOut(overshoot = 1.70158) {
  const s = overshoot;
  return function backOutEase(t) {
    const x = t - 1;
    return 1 + (s + 1) * x * x * x + s * x * x;
  };
}

export const easings = { linear, power2Out, power3Out, power2InOut, sineInOut, backOut };

export class TweenManager {
  constructor() {
    this.time = 0;
    this._list = [];
  }

  /**
   * 添加一条补间。
   * @param {object} spec
   *   from/to         起止值（数值）
   *   duration        时长（秒）
   *   delay           延迟（秒，相对 add 时刻）
   *   ease            缓动函数 (t)=>v
   *   onUpdate(v, eased, progress) 每帧回调
   *   onComplete(v)   完成回调（仅自然播完触发；被 cancel 不触发）
   *   tag             标记，可用 cancelTag 批量取消
   * @returns {{cancel: () => void, tag: string|null}}
   */
  add(spec = {}) {
    const tw = {
      from: num(spec.from, 0),
      to: num(spec.to, 1),
      duration: Math.max(0, num(spec.duration, 1)),
      delay: Math.max(0, num(spec.delay, 0)),
      ease: typeof spec.ease === "function" ? spec.ease : linear,
      onUpdate: typeof spec.onUpdate === "function" ? spec.onUpdate : null,
      onComplete: typeof spec.onComplete === "function" ? spec.onComplete : null,
      tag: spec.tag ?? null,
      spawn: this.time,
      done: false,
      cancelled: false,
    };
    this._list.push(tw);
    return {
      tag: tw.tag,
      cancel() {
        tw.cancelled = true;
      },
    };
  }

  /** 取消所有指定 tag 的补间（含未开始的） */
  cancelTag(tag) {
    for (const tw of this._list) {
      if (tw.tag === tag) tw.cancelled = true;
    }
  }

  /** 当前未完成（未取消）的补间数量 */
  get pending() {
    let n = 0;
    for (const tw of this._list) if (!tw.done && !tw.cancelled) n++;
    return n;
  }

  /** 丢弃全部补间 */
  clear() {
    this._list.length = 0;
  }

  /**
   * 推进时钟并派发回调。
   * @param {number} dtOrNow  默认当作增量秒数；absolute=true 时当作绝对时间
   * @param {boolean} absolute
   */
  update(dtOrNow, absolute = false) {
    if (absolute) this.time = num(dtOrNow, this.time);
    else this.time += num(dtOrNow, 0);

    const now = this.time;
    const list = this._list;

    // 正向遍历：onComplete 里新增的补间 spawn=当前时间，本轮最多再处理 delay=0 的一条起步帧
    for (let i = 0; i < list.length; i++) {
      const tw = list[i];
      if (tw.done || tw.cancelled) continue;
      const local = now - tw.spawn - tw.delay;
      if (local < 0) continue;

      let p = tw.duration > 0 ? local / tw.duration : 1;
      if (p > 1) p = 1;

      const eased = tw.ease(p);
      const v = tw.from + (tw.to - tw.from) * eased;

      if (tw.onUpdate) tw.onUpdate(v, eased, p);

      if (p >= 1) {
        tw.done = true;
        if (tw.onComplete && !tw.cancelled) tw.onComplete(v);
      }
    }

    // 清理已完成 / 已取消的条目
    for (let i = list.length - 1; i >= 0; i--) {
      const tw = list[i];
      if (tw.done || tw.cancelled) list.splice(i, 1);
    }
  }
}

export function createTweenManager() {
  return new TweenManager();
}

function num(v, fallback) {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}
