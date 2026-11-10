// ── 电莲花 · 程序化 WebAudio 引擎 ─────────────────────────────────────
// 零网络：所有音色由振荡器 / 本底噪声缓冲实时合成，无任何外部音频资源。
// 惰性初始化：AudioContext 在首次用户手势时创建（自动播放策略安全）。
// 自接线：initAudio() 订阅事件总线并绑定 UI 按钮，集成方只需调用一次。
//
// 对外契约：
//   createAudioEngine() → { init, setEnabled, setRpm, rev, revHoldStart, revHoldEnd,
//                           playTick, playSeatClick, playAssemble, playExplodeWhoosh,
//                           setAmbient, update, enabled/context/ambient (getter) }
//   initAudio() → engine（幂等，重复调用返回同一实例）
import { on } from "../events.js";

const Ctor = globalThis.AudioContext || globalThis.webkitAudioContext || null;

const MASTER = 0.9; // 主增益
const F_MIN = 80; // 电机基频下限 Hz
const F_MAX = 1400; // 电机基频上限 Hz
const AMBIENT_LEVEL = {
  // 各环境音总电平（out 增益目标）
  auto_show: 0.4,
  wind_tunnel: 0.28,
  studio: 0.6,
  night_road: 0.35,
};

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
// rpm → 基频：指数映射，端点精确 80 → 1400 Hz
const rpmFreq = (rpm) => F_MIN * Math.pow(F_MAX / F_MIN, rpm);

export function createAudioEngine() {
  let ctx = null;
  let master = null;
  let noiseBuf = null;
  let enabled = true;
  let dead = false; // AudioContext 不可用 / 初始化失败 → 全部静音降级

  // 电机层节点
  let osc1 = null;
  let osc2 = null;
  let motorBp = null;
  let motorGain = null;
  let currentGain = null;

  // rev 状态机（一次性扫频 / 长按保持）
  let hold = false;
  let sustaining = false;
  let revTimers = [];

  // 环境音
  let ambient = null;
  let ambientName = null;
  let pendingAmbient = null;

  // ── 初始化 ──────────────────────────────────────────────
  function ensure() {
    if (ctx) return ctx;
    if (dead) return null;
    if (!Ctor) {
      dead = true;
      return null;
    }
    try {
      ctx = new Ctor();
      master = ctx.createGain();
      master.gain.value = enabled ? MASTER : 0;
      const comp = ctx.createDynamicsCompressor(); // 轻度限幅，防叠音爆音
      comp.threshold.value = -20;
      comp.knee.value = 20;
      comp.ratio.value = 3;
      comp.attack.value = 0.006;
      comp.release.value = 0.25;
      master.connect(comp).connect(ctx.destination);
      makeNoiseBuffer();
      makeMotor();
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      if (pendingAmbient) {
        const n = pendingAmbient;
        pendingAmbient = null;
        setAmbient(n);
      }
    } catch (err) {
      console.warn("[audio] 初始化失败，进入静音降级:", err);
      dead = true;
      ctx = null;
      master = null;
    }
    return ctx;
  }

  function makeNoiseBuffer() {
    const len = Math.floor(ctx.sampleRate * 2); // 2s 白噪声，循环播放
    noiseBuf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  }

  function makeMotor() {
    // 双振荡器（锯齿 + 失谐正弦）→ 带通 → 电机增益
    motorGain = ctx.createGain();
    motorGain.gain.value = 0;
    motorBp = ctx.createBiquadFilter();
    motorBp.type = "bandpass";
    motorBp.frequency.value = F_MIN;
    motorBp.Q.value = 1.6;
    osc1 = ctx.createOscillator();
    osc1.type = "sawtooth";
    osc1.frequency.value = F_MIN;
    osc2 = ctx.createOscillator();
    osc2.type = "sine";
    osc2.frequency.value = F_MIN;
    osc2.detune.value = 9; // 失谐拍频
    const g1 = ctx.createGain();
    g1.gain.value = 0.5;
    const g2 = ctx.createGain();
    g2.gain.value = 0.7;
    osc1.connect(g1).connect(motorBp);
    osc2.connect(g2).connect(motorBp);
    motorBp.connect(motorGain).connect(master);
    // “电流声” 层：白噪声 → 2kHz 带通 → 随 rpm 缩放
    const src = ctx.createBufferSource();
    src.buffer = noiseBuf;
    src.loop = true;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = 2000;
    bp.Q.value = 0.8;
    currentGain = ctx.createGain();
    currentGain.gain.value = 0;
    src.connect(bp).connect(currentGain).connect(master);
    const t = ctx.currentTime;
    osc1.start(t);
    osc2.start(t);
    src.start(t);
  }

  // rpm 驱动：所有转速相关参数用 setTargetAtTime 平滑逼近（指数曲线）
  function driveRpm(v, tc) {
    if (!ctx) return;
    const t = ctx.currentTime;
    const f = rpmFreq(v);
    const go = (p, x) => {
      try {
        p.setTargetAtTime(x, t, tc);
      } catch (_) {
        /* 参数已释放等边界：忽略 */
      }
    };
    go(osc1.frequency, f);
    go(osc2.frequency, f);
    go(motorBp.frequency, f);
    go(motorGain.gain, 0.02 + 0.2 * v); // 待机微鸣 0.02
    go(currentGain.gain, 0.09 * v);
  }

  function clearRevTimers() {
    for (const id of revTimers) clearTimeout(id);
    revTimers = [];
  }

  // ── 对外方法 ────────────────────────────────────────────
  function init() {
    // ensure 只在“新建”时 resume；若 ctx 先前在非手势环境下创建（被挂起），
    // 真正的首次手势会再次调用 init —— 这里补一次 resume，避免永久静音。
    if (ensure() && ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
  }

  function setEnabled(v) {
    enabled = !!v;
    if (!ctx || !master) return;
    try {
      master.gain.setTargetAtTime(enabled ? MASTER : 0, ctx.currentTime, 0.05);
    } catch (_) {}
  }

  function setRpm(v) {
    if (!ensure()) return;
    clearRevTimers();
    hold = false;
    sustaining = false;
    driveRpm(clamp01(v), 0.05);
  }

  // 一次性轰鸣：0 → 0.85（约 0.45s）→ 0.15（至约 1.4s）→ 归零
  function rev() {
    if (!ensure()) return;
    clearRevTimers();
    driveRpm(0.85, 0.11);
    revTimers.push(
      setTimeout(() => {
        if (hold) {
          sustaining = true; // 长按：停在峰值直到松手
          return;
        }
        driveRpm(0.15, 0.34);
        revTimers.push(
          setTimeout(() => {
            if (!hold) driveRpm(0, 0.4);
          }, 950)
        );
      }, 450)
    );
  }

  // 长按保持（按钮 pointerdown）
  function revHoldStart() {
    if (!ensure()) return;
    hold = true;
    rev();
  }

  // 松手（按钮 pointerup / leave / cancel）
  function revHoldEnd() {
    hold = false;
    if (sustaining) {
      sustaining = false;
      clearRevTimers();
      if (ctx) driveRpm(0, 0.3);
    }
  }

  // 方波 blip 共用体：短促 UI 提示音
  function blip(t, freq, peak, holdMs, tailMs) {
    const osc = ctx.createOscillator();
    osc.type = "square";
    osc.frequency.value = freq;
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 4200;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + 0.004);
    g.gain.setValueAtTime(peak, t + holdMs / 1000);
    g.gain.exponentialRampToValueAtTime(0.0001, t + (holdMs + tailMs) / 1000);
    osc.connect(lp).connect(g).connect(master);
    osc.start(t);
    osc.stop(t + (holdMs + tailMs) / 1000 + 0.01);
  }

  function playTick(kind) {
    if (!ensure()) return;
    const t = ctx.currentTime;
    if (kind === "select") blip(t, 950, 0.06, 15, 40); // 选中：略低
    else if (kind === "soft") blip(t, 1100, 0.035, 12, 35); // 拾取：更轻
    else blip(t, 1200, 0.06, 15, 40);
  }

  // 零件入位“咔哒”：FM 金属音（载波 2400，调制比 1.7，指数衰减 40ms）+ 高通噪声 30ms
  function playSeatClick() {
    if (!ensure()) return;
    const t = ctx.currentTime;
    const carrier = ctx.createOscillator();
    carrier.type = "sine";
    carrier.frequency.value = 2400;
    const mod = ctx.createOscillator();
    mod.type = "sine";
    mod.frequency.value = 2400 * 1.7;
    const idx = ctx.createGain(); // 调制指数衰减
    idx.gain.setValueAtTime(1600, t);
    idx.gain.exponentialRampToValueAtTime(1, t + 0.04);
    mod.connect(idx).connect(carrier.frequency);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.24, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    carrier.connect(g).connect(master);
    const ns = ctx.createBufferSource();
    ns.buffer = noiseBuf;
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 2200;
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(0.0001, t);
    ng.gain.exponentialRampToValueAtTime(0.07, t + 0.003);
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.033);
    ns.connect(hp).connect(ng).connect(master);
    carrier.start(t);
    mod.start(t);
    carrier.stop(t + 0.14);
    mod.stop(t + 0.14);
    ns.start(t);
    ns.stop(t + 0.05);
  }

  // 合拢：更柔的双击 + 90Hz 低频轻震
  function playAssemble() {
    if (!ensure()) return;
    const t = ctx.currentTime;
    blip(t, 780, 0.04, 12, 35);
    blip(t + 0.085, 660, 0.03, 12, 35);
    const s = ctx.createOscillator();
    s.type = "sine";
    s.frequency.value = 90;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
    s.connect(g).connect(master);
    s.start(t);
    s.stop(t + 0.22);
  }

  // 拆解：0.9s 噪声带通扫频 300→3000Hz + 伺服哨音 220→440Hz
  function playExplodeWhoosh() {
    if (!ensure()) return;
    const t = ctx.currentTime;
    const ns = ctx.createBufferSource();
    ns.buffer = noiseBuf;
    ns.loop = true;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.Q.value = 0.9;
    bp.frequency.setValueAtTime(300, t);
    bp.frequency.exponentialRampToValueAtTime(3000, t + 0.9);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.15, t + 0.22);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    ns.connect(bp).connect(g).connect(master);
    ns.start(t);
    ns.stop(t + 0.95);
    const so = ctx.createOscillator();
    so.type = "sine";
    so.frequency.setValueAtTime(220, t);
    so.frequency.exponentialRampToValueAtTime(440, t + 0.9);
    const sg = ctx.createGain();
    sg.gain.setValueAtTime(0.0001, t);
    sg.gain.exponentialRampToValueAtTime(0.03, t + 0.1);
    sg.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    so.connect(sg).connect(master);
    so.start(t);
    so.stop(t + 0.95);
  }

  // ── 环境音 ──────────────────────────────────────────────
  function buildAmbient(name) {
    const h = { out: ctx.createGain(), sources: [], timer: 0 };
    h.out.gain.value = 0;
    h.out.connect(master);
    const start = (n) => {
      n.start(ctx.currentTime);
      h.sources.push(n);
    };
    const mkNoise = () => {
      const s = ctx.createBufferSource();
      s.buffer = noiseBuf;
      s.loop = true;
      return s;
    };

    if (name === "auto_show") {
      // 车展展厅：55Hz 低鸣 + 微弱谐波 + 大厅底噪
      const hum = ctx.createOscillator();
      hum.type = "sine";
      hum.frequency.value = 55;
      const hg = ctx.createGain();
      hg.gain.value = 0.25;
      hum.connect(hg).connect(h.out);
      start(hum);
      const harm = ctx.createOscillator();
      harm.type = "sine";
      harm.frequency.value = 110;
      const hag = ctx.createGain();
      hag.gain.value = 0.06;
      harm.connect(hag).connect(h.out);
      start(harm);
      const n = mkNoise();
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.value = 650;
      bp.Q.value = 0.6;
      const ng = ctx.createGain();
      ng.gain.value = 0.05;
      n.connect(bp).connect(ng).connect(h.out);
      start(n);
    } else if (name === "wind_tunnel") {
      // 深夜风洞：气流噪声 + 缓慢扫频带通（0.05Hz LFO）
      const n = mkNoise();
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.value = 700;
      bp.Q.value = 1.1;
      const ng = ctx.createGain();
      ng.gain.value = 0.5;
      n.connect(bp).connect(ng).connect(h.out);
      start(n);
      const lfo = ctx.createOscillator();
      lfo.type = "sine";
      lfo.frequency.value = 0.05;
      const depth = ctx.createGain();
      depth.gain.value = 450;
      lfo.connect(depth).connect(bp.frequency);
      start(lfo);
    } else if (name === "night_road") {
      // 山路夜景：柔风噪声 + 稀疏蟋蟀脉冲串（4.2kHz 正弦簇）
      const n = mkNoise();
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.value = 380;
      bp.Q.value = 0.5;
      const ng = ctx.createGain();
      ng.gain.value = 0.35;
      n.connect(bp).connect(ng).connect(h.out);
      start(n);
      const chirp = () => {
        const t0 = ctx.currentTime;
        for (let i = 0; i < 3; i++) {
          const o = ctx.createOscillator();
          o.type = "sine";
          o.frequency.value = 4200;
          const g = ctx.createGain();
          const st = t0 + i * 0.07;
          g.gain.setValueAtTime(0.0001, st);
          g.gain.exponentialRampToValueAtTime(0.12, st + 0.006);
          g.gain.exponentialRampToValueAtTime(0.0001, st + 0.05);
          o.connect(g).connect(h.out);
          o.start(st);
          o.stop(st + 0.06);
        }
        h.timer = setTimeout(chirp, 1200 + Math.random() * 1600);
      };
      h.timer = setTimeout(chirp, 800 + Math.random() * 1200);
    } else {
      // studio（默认兜底）：极低底噪，近似无声
      const n = mkNoise();
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = 300;
      const ng = ctx.createGain();
      ng.gain.value = 0.05;
      n.connect(lp).connect(ng).connect(h.out);
      start(n);
    }
    return h;
  }

  function disposeAmbient(h) {
    if (!h) return;
    if (h.timer) clearTimeout(h.timer);
    for (const s of h.sources) {
      try {
        s.stop();
      } catch (_) {}
    }
    try {
      h.out.disconnect();
    } catch (_) {}
  }

  // 环境音切换：1.2s 线性交叉淡入淡出
  function setAmbient(name) {
    if (!name) return;
    if (!ensure()) {
      pendingAmbient = name;
      return;
    }
    if (name === ambientName && ambient) return;
    const t = ctx.currentTime;
    const prev = ambient;
    ambientName = name;
    const level = AMBIENT_LEVEL[name] != null ? AMBIENT_LEVEL[name] : 0.3;
    const h = buildAmbient(name);
    h.out.gain.setValueAtTime(0, t);
    h.out.gain.linearRampToValueAtTime(level, t + 1.2);
    ambient = h;
    if (prev) {
      try {
        prev.out.gain.cancelAndHoldAtTime(t); // 保持当前值再淡出，避免咔嗒
      } catch (_) {
        try {
          prev.out.gain.cancelScheduledValues(t);
        } catch (_) {}
      }
      prev.out.gain.linearRampToValueAtTime(0, t + 1.2);
      setTimeout(() => disposeAmbient(prev), 1300);
    }
  }

  // 预留：未来可接入转速平滑 / 帧时钟，当前无操作
  function update(_dt) {}

  return {
    init,
    setEnabled,
    setRpm,
    rev,
    revHoldStart,
    revHoldEnd,
    playTick,
    playSeatClick,
    playAssemble,
    playExplodeWhoosh,
    setAmbient,
    update,
    get enabled() {
      return enabled;
    },
    get context() {
      return ctx;
    },
    get ambient() {
      return ambientName;
    },
  };
}

// ── 一次性接线入口：事件总线 + UI 按钮 + 首次手势初始化 ──────────────
let sharedInstance = null;

export function initAudio() {
  if (sharedInstance) return sharedInstance;

  const engine = createAudioEngine();

  // 事件总线自订阅（src/events.js）
  on("part:seated", () => engine.playSeatClick());
  on("explode:start", () => engine.playExplodeWhoosh());
  on("assemble:start", () => engine.playAssemble());
  on("audio:tick", (p) => engine.playTick(p && p.action));
  on("background:switch", (p) => engine.setAmbient(p && p.name));
  on("paint:changed", () => engine.playTick("select"));
  on("accessory:changed", () => engine.playTick("select"));
  on("part:pick", () => engine.playTick("soft"));

  if (typeof document !== "undefined") {
    // 声音开关：aria-pressed / is-active 与引擎状态双向一致
    const audioBtn = document.querySelector('button[data-action="audio"]');
    if (audioBtn) {
      audioBtn.setAttribute("aria-pressed", String(engine.enabled));
      audioBtn.classList.toggle("is-active", engine.enabled);
      audioBtn.addEventListener("click", () => {
        engine.init();
        engine.setEnabled(!engine.enabled);
        const sync = () => {
          audioBtn.setAttribute("aria-pressed", String(engine.enabled));
          audioBtn.classList.toggle("is-active", engine.enabled);
        };
        sync();
        setTimeout(sync, 0); // 防与其他绑定同拍冲突，末端重同步
      });
    }

    // 电机轰鸣：按住持续（pointerdown → rev 峰值保持；松手回落）
    const revBtn = document.querySelector('button[data-action="rev"]');
    if (revBtn) {
      const down = () => {
        engine.init();
        engine.revHoldStart();
      };
      const up = () => engine.revHoldEnd();
      revBtn.addEventListener("pointerdown", down);
      revBtn.addEventListener("pointerup", up);
      revBtn.addEventListener("pointerleave", up);
      revBtn.addEventListener("pointercancel", up);
      revBtn.addEventListener("keydown", (e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          down();
        }
      });
      revBtn.addEventListener("keyup", (e) => {
        if (e.key === " " || e.key === "Enter") up();
      });
    }

    // 首次用户手势惰性创建 AudioContext 并恢复（自动播放策略安全）
    const boot = () => engine.init();
    window.addEventListener("pointerdown", boot, { once: true, capture: true });
    window.addEventListener("keydown", boot, { once: true, capture: true });
  }

  sharedInstance = engine;
  return engine;
}
