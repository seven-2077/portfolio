/* 电莲花 ·三层车漆材质（metal flake + clearcoat fresnel + env reflection）
 *
 * 交付物 1：
 *  - createPaintMaterial()  → MeshPhysicalMaterial，注入金属薄片 GLSL
 *  - setPaint({hue,saturation,metalness,clearcoat,clearcoatRoughness?}) 平滑改色
 *  - PAINT_PRESETS 四套漆面预设
 *  - applyRoles(carRoot) 按 userData.materialRole 分组，共享材质实例
 *
 * 顶层无 DOM / WebGL 访问（全部在函数内），可被 node 直接 import 冒烟。
 */
import * as THREE from "three";

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const TWEEN_MS = 250; // ~0.25s 平滑过渡

/* ------------------------------------------------------------------ *
 * 金属薄片（metal flake）注入用 uniform —— 常驻对象，编译后可直接改 value
 * ------------------------------------------------------------------ */
const flakeUniforms = {
  uFlakeScale: { value: 46.0 },        // 世界空间薄片网格密度
  uFlakeDensity: { value: 0.52 },      // 活跃薄片阈值（避免满屏噪点）
  uFlakeJitter: { value: 0.62 },       // 薄片法线扰动幅度
  uGlintPower: { value: 92.0 },        // 高光锐度（越大约越“碎钻”）
  uSparkleStrength: { value: 0.75 },   // 闪光强度（克制）
  uLightDir: { value: new THREE.Vector3(0.35, 0.86, 0.36).normalize() },
  uBackLightDir: { value: new THREE.Vector3(-0.55, 0.3, -0.72).normalize() },
  uFlakeTint: { value: new THREE.Color(1.0, 1.0, 1.0) },
  uFresnelStrength: { value: 0.16 },   // wet-look 边缘增强
  uFresnelTint: { value: new THREE.Color(0.78, 0.88, 1.0) },
};

const VERT_PARS = /* glsl */ `
varying vec3 vFlakeWorldPos;
varying vec3 vFlakeWorldNormal;
`;

const VERT_BODY = /* glsl */ `
vFlakeWorldPos = ( modelMatrix * vec4( transformed, 1.0 ) ).xyz;
vFlakeWorldNormal = normalize( mat3( modelMatrix ) * objectNormal );
`;

const FRAG_PARS = /* glsl */ `
varying vec3 vFlakeWorldPos;
varying vec3 vFlakeWorldNormal;
uniform float uFlakeScale;
uniform float uFlakeDensity;
uniform float uFlakeJitter;
uniform float uGlintPower;
uniform float uSparkleStrength;
uniform vec3 uLightDir;
uniform vec3 uBackLightDir;
uniform vec3 uFlakeTint;
uniform float uFresnelStrength;
uniform vec3 uFresnelTint;

vec3 el_hash33( vec3 p ) {
  p = fract( p * vec3( 443.897, 441.423, 437.195 ) );
  p += dot( p, p.yxz + 19.19 );
  return fract( ( p.xxy + p.yxx ) * p.zyx );
}
`;

/* 在 outgoingLight 最终确定（clearcoat / sheen 之后、opaque_fragment 之前）叠加：
 * 1) 视角相关金属薄片闪烁 —— 每个世界网格单元一枚随机取向薄片，
 *    沿 key / backlight 方向的镜面高光锐利 pow，形成随视角滚动的碎钻感。
 * 2) fresnel 湿润边缘增强。 */
const FRAG_BODY = /* glsl */ `
{
  vec3 Nw = normalize( vFlakeWorldNormal );
  vec3 V  = normalize( cameraPosition - vFlakeWorldPos );
  vec3 cell = floor( vFlakeWorldPos * uFlakeScale );
  vec3 rnd = el_hash33( cell );
  float flakeOn = step( uFlakeDensity, rnd.x );
  vec3 flakeN = normalize( Nw + ( rnd - 0.5 ) * uFlakeJitter );
  vec3 R = reflect( -V, flakeN );
  float key  = pow( max( dot( R, uLightDir ), 0.0 ), uGlintPower );
  float back = pow( max( dot( R, uBackLightDir ), 0.0 ), uGlintPower * 0.6 );
  float sparkle = flakeOn * ( key + back * 0.7 ) * uSparkleStrength;
  float fres = pow( 1.0 - max( dot( V, Nw ), 0.0 ), 4.0 );
  outgoingLight += uFlakeTint * sparkle;
  outgoingLight += uFresnelTint * fres * uFresnelStrength;
}
`;

/* ------------------------------------------------------------------ *
 * 漆面状态（target = 期望值；current = 当前插值到的值）
 * ------------------------------------------------------------------ */
const _target = {
  hue: 0.085, saturation: 0.92, lightness: 0.55,
  metalness: 0.9, clearcoat: 1.0, clearcoatRoughness: 0.03,
  iridescence: 0.0, roughness: 0.22,
};
const _current = { ..._target };
let _from = { ..._current };
let _paint = null;
let _raf = 0;
let _t0 = 0;

function _hexToHsl(hex) {
  const c = new THREE.Color(hex);
  const t = { h: 0, s: 0, l: 0 };
  c.getHSL(t, THREE.SRGBColorSpace);
  return t;
}

function _applyState(mat, s) {
  mat.color.setHSL(s.hue, s.saturation, s.lightness, THREE.SRGBColorSpace);
  mat.metalness = s.metalness;
  mat.clearcoat = s.clearcoat;
  mat.clearcoatRoughness = s.clearcoatRoughness;
  mat.iridescence = s.iridescence;
  mat.roughness = s.roughness;
}

function _tick(now) {
  const t = clamp((now - _t0) / TWEEN_MS, 0, 1);
  const k = 1 - Math.pow(1 - t, 3); // ease-out cubic
  let dh = _target.hue - _from.hue;
  if (dh > 0.5) dh -= 1; else if (dh < -0.5) dh += 1;
  _current.hue = (((_from.hue + dh * k) % 1) + 1) % 1;
  _current.saturation = lerp(_from.saturation, _target.saturation, k);
  _current.lightness = lerp(_from.lightness, _target.lightness, k);
  _current.metalness = lerp(_from.metalness, _target.metalness, k);
  _current.clearcoat = lerp(_from.clearcoat, _target.clearcoat, k);
  _current.clearcoatRoughness = lerp(_from.clearcoatRoughness, _target.clearcoatRoughness, k);
  _current.iridescence = lerp(_from.iridescence, _target.iridescence, k);
  _current.roughness = lerp(_from.roughness, _target.roughness, k);
  if (_paint) _applyState(_paint, _current);
  if (t < 1) { _raf = requestAnimationFrame(_tick); }
  else { _raf = 0; Object.assign(_current, _target); if (_paint) _applyState(_paint, _current); }
}

function _startTween() {
  if (!_paint) return; // 材质尚未创建，createPaintMaterial 时会应用 _current
  if (typeof requestAnimationFrame !== "function" || typeof performance === "undefined") {
    Object.assign(_current, _target);
    _applyState(_paint, _current);
    return;
  }
  _from = { ..._current };
  _t0 = performance.now();
  if (!_raf) _raf = requestAnimationFrame(_tick);
}

/* ------------------------------------------------------------------ *
 * createPaintMaterial
 * ------------------------------------------------------------------ */
export function createPaintMaterial() {
  if (_paint) return _paint;

  const m = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color().setHSL(_target.hue, _target.saturation, _target.lightness, THREE.SRGBColorSpace),
    metalness: _target.metalness,
    roughness: _target.roughness,
    clearcoat: _target.clearcoat,
    clearcoatRoughness: _target.clearcoatRoughness,
    iridescence: _target.iridescence,
    envMapIntensity: 1.2, // 反射读得出来
  });

  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, flakeUniforms);

    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\n" + VERT_PARS)
      .replace("#include <project_vertex>", "#include <project_vertex>\n" + VERT_BODY);

    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\n" + FRAG_PARS)
      .replace(
        "#include <opaque_fragment>",
        FRAG_BODY + "\n#include <opaque_fragment>",
      );
  };
  m.customProgramCacheKey = () => "electric-lotus-paint-v1";

  _paint = m;
  _applyState(m, _current);
  return m;
}

/* ------------------------------------------------------------------ *
 * setPaint —— 平滑（~0.25s）更新，值全部 clamp，无闪烁
 * ------------------------------------------------------------------ */
export function setPaint(params = {}) {
  const p = _target;
  if (params.hue !== undefined) p.hue = clamp(params.hue, 0, 1);
  if (params.saturation !== undefined) p.saturation = clamp(params.saturation, 0, 1);
  if (params.lightness !== undefined) p.lightness = clamp(params.lightness, 0, 1);
  if (params.metalness !== undefined) p.metalness = clamp(params.metalness, 0, 1);
  if (params.clearcoat !== undefined) p.clearcoat = clamp(params.clearcoat, 0, 1);
  if (params.clearcoatRoughness !== undefined) p.clearcoatRoughness = clamp(params.clearcoatRoughness, 0, 1);
  if (params.iridescence !== undefined) p.iridescence = clamp(params.iridescence, 0, 1);
  if (params.roughness !== undefined) p.roughness = clamp(params.roughness, 0, 1);
  _startTween();
  return { ..._target };
}

/* ------------------------------------------------------------------ *
 * PAINT_PRESETS
 * ------------------------------------------------------------------ */
function _preset(id, name, hex, extra) {
  const hsl = _hexToHsl(hex);
  return {
    id, name, color: hex,
    hue: hsl.h, saturation: hsl.s, lightness: hsl.l,
    ...extra,
  };
}

export const PAINT_PRESETS = [
  _preset("lotus_yellow", "莲花黄", 0xffb454, {
    metalness: 0.9, clearcoat: 1.0, clearcoatRoughness: 0.03, roughness: 0.22, iridescence: 0.0,
  }),
  _preset("meteor_grey", "陨石灰", 0x3a3f47, {
    metalness: 0.7, clearcoat: 0.4, clearcoatRoughness: 0.5, roughness: 0.4, iridescence: 0.0,
  }),
  _preset("pearl_white", "珍珠白", 0xf2f3f1, {
    metalness: 0.4, clearcoat: 1.0, clearcoatRoughness: 0.06, roughness: 0.25, iridescence: 0.35,
  }),
  _preset("track_green", "赛道绿", 0x1f7a3f, {
    metalness: 0.85, clearcoat: 1.0, clearcoatRoughness: 0.04, roughness: 0.24, iridescence: 0.0,
  }),
];

export function applyPreset(id) {
  const p = PAINT_PRESETS.find((x) => x.id === id);
  if (!p) return null;
  setPaint(p);
  return p;
}

/* ------------------------------------------------------------------ *
 * applyRoles —— 按 materialRole 分组并共享材质实例
 * ------------------------------------------------------------------ */
let _shared = null;
function _sharedMats() {
  if (_shared) return _shared;

  const glass = new THREE.MeshPhysicalMaterial({
    color: 0x0a0e14, transparent: true, opacity: 0.35,
    roughness: 0.05, metalness: 0.0, ior: 1.45,
    envMapIntensity: 1.2, depthWrite: false,
  });
  const trim = new THREE.MeshStandardMaterial({
    color: 0x14161a, roughness: 0.6, metalness: 0.0, envMapIntensity: 0.8,
  });
  const metal = new THREE.MeshStandardMaterial({
    color: 0x9aa0a6, roughness: 0.35, metalness: 1.0, envMapIntensity: 1.0,
  });
  const tire = new THREE.MeshStandardMaterial({
    color: 0x0a0a0c, roughness: 0.9, metalness: 0.0, envMapIntensity: 0.5,
  });
  const carbon = new THREE.MeshPhysicalMaterial({
    color: 0x2a2d33, roughness: 0.35, metalness: 0.5,
    clearcoat: 0.5, clearcoatRoughness: 0.25,
    sheen: 0.3, sheenRoughness: 0.5, sheenColor: new THREE.Color(0x6a7080),
    envMapIntensity: 1.0,
  });
  const lightFront = new THREE.MeshStandardMaterial({
    color: 0x1a1408, emissive: 0xffd9a0, emissiveIntensity: 2.6,
    roughness: 0.3, metalness: 0.0,
  });
  const lightRear = new THREE.MeshStandardMaterial({
    color: 0x180604, emissive: 0xff4a3a, emissiveIntensity: 2.6,
    roughness: 0.3, metalness: 0.0,
  });

  _shared = { glass, trim, metal, tire, carbon, lightFront, lightRear };
  return _shared;
}

export function applyRoles(carRoot) {
  const paint = createPaintMaterial();
  const s = _sharedMats();

  carRoot.traverse((o) => {
    if (!o.isMesh) return;
    const role = o.userData && o.userData.materialRole;
    if (!role) return;
    switch (role) {
      case "paint": o.material = paint; break;
      case "glass": o.material = s.glass; break;
      case "trim": o.material = s.trim; break;
      case "metal": o.material = s.metal; break;
      case "tire": o.material = s.tire; break;
      case "carbon": o.material = s.carbon; break;
      case "light": {
        const pn = o.userData.partName || "";
        o.material = pn.startsWith("light_rear") ? s.lightRear : s.lightFront;
        break;
      }
      default: break;
    }
  });

  return {
    paint,
    glass: s.glass, trim: s.trim, metal: s.metal,
    tire: s.tire, carbon: s.carbon,
    lightFront: s.lightFront, lightRear: s.lightRear,
  };
}
