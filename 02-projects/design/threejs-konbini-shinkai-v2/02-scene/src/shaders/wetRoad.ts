import {
  Color,
  Matrix4,
  PlaneGeometry,
  ShaderMaterial,
  Vector2,
  Vector3,
  Vector4,
  type Camera,
  type Scene,
  type Texture,
  type WebGLRenderer,
} from 'three';
import { Reflector } from 'three/addons/objects/Reflector.js';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';

/**
 * True planar reflection (Reflector) blended with procedural wet asphalt
 * and irregular puddle masks. This is the still-frame ground hero.
 */
const wetFrag = /* glsl */ `
uniform vec3 color;
uniform sampler2D tDiffuse;
uniform float uWetness;
uniform vec3 uSkyHorizon;
uniform vec3 uSkyZenith;
uniform vec3 uSunColor;
uniform vec3 uLampTint;
uniform float uNight;
uniform vec2 uMapScale;
uniform sampler2D uSignMap;
uniform float uHasSign;

varying vec4 vUv;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
varying vec3 vViewDir;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}
float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p *= 2.07;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 wp = vWorldPos.xz * uMapScale;

  // Long puddles / a wet ribbon toward the entrance, not a cloudy mottling
  float puddle = smoothstep(0.58, 0.8, fbm(vec2(wp.x * 1.15, wp.y * 0.18) + 3.1));
  float guide = exp(-pow((vWorldPos.x - 0.15) * 0.13, 2.0)) * smoothstep(18.0, 2.2, vWorldPos.z);
  puddle = max(puddle * 0.7, guide);
  puddle *= smoothstep(0.1, 0.38, uWetness);
  float wetField = mix(0.88 * uWetness, 1.0, puddle);

  float ripple = (noise(wp * 16.0) - 0.5) * 0.0024 * puddle * uWetness;
  float ripple2 = (fbm(wp * 9.0 + 2.7) - 0.5) * 0.0016 * puddle * uWetness;
  vec4 uvS = vUv;
  uvS.xy += (ripple + ripple2) * uvS.w;
  vec4 refl = texture2DProj(tDiffuse, uvS);

  float agg = noise(wp * 34.0);
  // Soften the left-foreground grit without changing the road model
  float fleck = smoothstep(0.9, 0.98, noise(wp * 80.0));
  fleck *= mix(0.2, 1.0, smoothstep(-9.0, 1.5, vWorldPos.x));
  vec3 dry = color * (0.62 + agg * 0.08);
  dry += vec3(0.016, 0.016, 0.018) * fleck;

  vec3 wetCol = dry * vec3(0.16, 0.18, 0.22);

  vec3 n = normalize(vWorldNormal);
  vec3 v = normalize(vViewDir);
  float fres = pow(1.0 - max(0.0, dot(n, v)), 1.8);

  // Rain dusk: the road is a mirror first, asphalt second
  float mirror = mix(0.55, 0.93, fres) * wetField;
  mirror = max(mirror, mix(0.8, 0.97, fres) * puddle * uWetness);

  vec3 asphalt = mix(dry, wetCol, wetField);
  vec3 refCol = refl.rgb * 1.1;

  // Projected reflections of the sign (higher) and window band (lower) onto y=0
  vec3 cam = cameraPosition;
  vec2 along = normalize(vec2(0.0, 0.4) - cam.xz);
  vec2 across = vec2(-along.y, along.x);
  float tSign = clamp(cam.y / max(cam.y + 2.2, 0.2), 0.05, 0.95);
  vec2 signHit = mix(cam.xz, vec2(0.0, 0.44), tSign);
  float tWin = clamp(cam.y / max(cam.y + 1.35, 0.2), 0.05, 0.95);
  vec2 winHit = mix(cam.xz, vec2(0.0, 0.12), tWin);

  vec2 dS = vWorldPos.xz - signHit;
  float signMask = exp(-pow(dot(dS, across) / 1.4, 2.0)) * exp(-pow(dot(dS, along) / 0.5, 2.0));
  vec3 signGlow = vec3(0.96, 0.92, 0.86) * signMask * 0.28 * uWetness;
  float redMask = exp(-pow(dot(dS, across) / 1.35, 2.0)) * exp(-pow((dot(dS, along) - 0.22) / 0.1, 2.0));
  signGlow += vec3(0.58, 0.14, 0.12) * redMask * 0.4 * uWetness;

  // Soft projected lightbox: bright glyphs / red ends, not a hard white plate
  float tTop = clamp(cam.y / max(cam.y + 2.5, 0.2), 0.05, 0.95);
  float tBot = clamp(cam.y / max(cam.y + 1.9, 0.2), 0.05, 0.95);
  vec2 hitTop = mix(cam.xz, vec2(0.0, 0.44), tTop);
  vec2 hitBot = mix(cam.xz, vec2(0.0, 0.44), tBot);
  float alongSpan = max(length(hitTop - hitBot) * 0.5, 0.04);
  float sx = dot(dS, across) / max(tSign, 0.05);
  float syN = dot(vWorldPos.xz - mix(hitBot, hitTop, 0.5), along) / alongSpan;
  // Flip UV so the puddle reads 日曜 the right way up, not a mirrored stamp
  vec2 signUv = vec2(sx / 4.325 * 0.5 + 0.5, syN * 0.5 + 0.5);
  // Mild water warp: keep 日曜 readable, break the postage-stamp edge
  float warp = (fbm(wp * 7.5 + 1.3) - 0.5) * 0.018 * uWetness;
  signUv.x += warp * 0.4 + ripple * 3.5;
  signUv.y += warp * 0.55 + (noise(wp * 14.0) - 0.5) * 0.016 * uWetness;
  signUv.y = (signUv.y - 0.5) * 0.92 + 0.5;
  float rect = (1.0 - smoothstep(0.88, 1.42, abs(sx / 4.325)))
             * (1.0 - smoothstep(0.78, 1.55, abs(syN)));
  rect *= 0.8 + 0.2 * puddle;
  if (uHasSign > 0.5 && rect > 0.0) {
    vec2 px = vec2(0.008, 0.016);
    vec3 signTex = 0.2 * (
      texture2D(uSignMap, clamp(signUv, 0.0, 1.0)).rgb +
      texture2D(uSignMap, clamp(signUv + vec2(px.x, 0.0), 0.0, 1.0)).rgb +
      texture2D(uSignMap, clamp(signUv - vec2(px.x, 0.0), 0.0, 1.0)).rgb +
      texture2D(uSignMap, clamp(signUv + vec2(0.0, px.y), 0.0, 1.0)).rgb +
      texture2D(uSignMap, clamp(signUv - vec2(0.0, px.y), 0.0, 1.0)).rgb
    );
    float luma = dot(signTex, vec3(0.299, 0.587, 0.114));
    float glyph = smoothstep(0.55, 0.86, luma);
    float redEnd = smoothstep(0.1, 0.3, signTex.r - signTex.g);
    vec3 contrib = signTex * (0.06 + glyph * 0.8 + redEnd * 0.45);
    signGlow = mix(signGlow, contrib, clamp(rect * uWetness * 0.64, 0.0, 1.0));
  }

  vec2 dW = vWorldPos.xz - winHit;
  float winMask = exp(-pow(dot(dW, across) / 2.15, 2.0)) * exp(-pow(dot(dW, along) / 1.0, 2.0));
  signGlow += vec3(1.0, 0.86, 0.68) * winMask * 0.32 * uWetness;

  refCol += signGlow;
  refCol += uSunColor * pow(max(0.0, v.y), 5.0) * 0.08 * uWetness;

  // Soften left-foreground sakura sparkle in the puddle, keep the road model
  float leftSpec = (1.0 - smoothstep(-8.5, 0.8, vWorldPos.x)) * smoothstep(2.0, 9.0, vWorldPos.z);
  refCol = mix(refCol, mix(refCol, asphalt, 0.4), leftSpec * 0.55);

  vec3 col = mix(asphalt, refCol, clamp(mirror, 0.0, 1.0));
  col = mix(col, col + signGlow, 0.22 * uWetness);

  gl_FragColor = vec4(col, 1.0);

  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

const wetVert = /* glsl */ `
uniform mat4 textureMatrix;
varying vec4 vUv;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
varying vec3 vViewDir;

void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorldPos = world.xyz;
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  vViewDir = cameraPosition - world.xyz;
  vUv = textureMatrix * world;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

export function createWetRoad(width = 42, depth = 36): Reflector {
  const geo = new PlaneGeometry(width, depth, 1, 1);
  geo.rotateX(-Math.PI / 2);

  const reflector = new Reflector(geo, {
    clipBias: 0.003,
    textureWidth: 1024,
    textureHeight: 1024,
    multisample: 0,
    color: new Color(Hex.wetBlack),
    shader: {
      uniforms: {
        color: { value: new Color(Hex.wetBlack) },
        tDiffuse: { value: null },
        textureMatrix: { value: new Matrix4() },
        uWetness: { value: 1 },
        uSkyHorizon: { value: new Color(Hex.amberKey) },
        uSkyZenith: { value: new Color(Hex.deepIndigo) },
        uSunColor: { value: new Color(0xffd2a0) },
        uLampTint: { value: new Color(Hex.warmPaper) },
        uNight: { value: 0.6 },
        uMapScale: { value: new Vector2(1, 1) },
        uSignMap: { value: null },
        uHasSign: { value: 0 },
      },
      vertexShader: wetVert,
      fragmentShader: wetFrag,
    },
  });
  reflector.name = 'wet_road';
  reflector.position.set(0, 0, 3.2);
  // Shader already includes tonemapping + colorspace chunks
  (reflector.material as ShaderMaterial).toneMapped = false;
  return reflector;
}

export function applyWetRoad(road: Reflector, u: EnvUniformSnapshot): void {
  const mat = road.material as ShaderMaterial;
  if (!mat.uniforms.uWetness) return;
  mat.uniforms.uWetness.value = u.wetness;
  (mat.uniforms.uSkyHorizon.value as Color).setRGB(
    u.skyHorizon[0],
    u.skyHorizon[1],
    u.skyHorizon[2],
  );
  (mat.uniforms.uSkyZenith.value as Color).setRGB(
    u.skyZenith[0],
    u.skyZenith[1],
    u.skyZenith[2],
  );
  (mat.uniforms.uSunColor.value as Color).setRGB(
    u.sunColor[0],
    u.sunColor[1],
    u.sunColor[2],
  );
  mat.uniforms.uNight.value = u.nightFactor;
}

/** Keep TypeScript quiet if these three.js types are referenced later. */
export type RoadUpdateCtx = {
  renderer: WebGLRenderer;
  scene: Scene;
  camera: Camera;
  viewport?: Vector4;
  eye?: Vector3;
};


export function setWetRoadSignMap(road: Reflector, map: Texture | null): void {
  const mat = road.material as ShaderMaterial;
  if (!mat.uniforms.uSignMap) return;
  mat.uniforms.uSignMap.value = map;
  mat.uniforms.uHasSign.value = map ? 1 : 0;
}

export function createSidewalkMaterialColor(): number {
  return 0x6a6762;
}
