import {
  BackSide,
  Color,
  Mesh,
  ShaderMaterial,
  SphereGeometry,
  Vector3,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';

/**
 * Multi-layer Shinkai sky: zenith/horizon, sakura belt, cirrus + cumulus,
 * sun rim, crepuscular shafts, stars/moon, air-purple horizon veil.
 */
const vert = /* glsl */ `
varying vec3 vWorldDir;

void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorldDir = normalize(world.xyz - cameraPosition);
  vec4 clip = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_Position = clip.xyww;
}
`;

const frag = /* glsl */ `
precision highp float;

uniform vec3 uZenith;
uniform vec3 uHorizon;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform float uSunIntensity;
uniform float uNightFactor;
uniform float uTwilight;
uniform float uCloud;
uniform float uSeasonT;
uniform vec3 uFogColor;
uniform float uFogDensity;
uniform vec3 uAmber;
uniform vec3 uSakura;
uniform vec3 uAirPurple;
uniform float uGodray;
uniform float uTime;

varying vec3 vWorldDir;

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
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 6; i++) {
    v += a * noise(p);
    p = m * p;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec3 dir = normalize(vWorldDir);
  float elev = dir.y;
  vec3 sunD = normalize(uSunDir);

  // Base gradient — deep indigo zenith into warm/cool horizon
  float h = smoothstep(-0.05, 0.62, elev);
  vec3 col = mix(uHorizon, uZenith, pow(h, 0.7));

  // Amber belt hugging the horizon
  float amberBand = exp(-pow(elev - 0.02, 2.0) * 16.0) * max(uTwilight, 0.15);
  col = mix(col, uAmber, amberBand * 0.92);

  // Sakura waist just above amber
  float sakuraBand = exp(-pow(elev - 0.11, 2.0) * 26.0) * max(uTwilight, 0.12);
  col = mix(col, uSakura, sakuraBand * 0.5 * (1.0 - uNightFactor * 0.25));

  // Cool blue-hour ribbon above the warm belts
  float blueHour = exp(-pow(elev - 0.22, 2.0) * 32.0) * uTwilight * (0.45 + uNightFactor * 0.55);
  col = mix(col, vec3(0.18, 0.28, 0.52), blueHour * 0.42);

  // Spherical cloud UVs
  float az = atan(dir.z, dir.x);
  float el = asin(clamp(elev, -1.0, 1.0));
  vec2 cuv = vec2(az * 1.45, el * 3.4);

  // Cirrus — high, streaky, always a little present
  float cirrusMask = smoothstep(0.22, 0.48, elev) * (1.0 - smoothstep(0.72, 0.98, elev));
  vec2 cirrUV = vec2(cuv.x * 0.9 + cuv.y * 1.8, cuv.y * 0.45) + vec2(uSeasonT * 0.4, 0.0);
  float cirrus = smoothstep(0.48, 0.78, fbm(cirrUV * 2.4)) * cirrusMask * mix(0.25, 0.7, uCloud);

  // Cumulus — mid, puffier, denser in rain
  float cumulusMask = smoothstep(0.02, 0.28, elev) * (1.0 - smoothstep(0.48, 0.78, elev));
  float dens = fbm(cuv * 2.15 + vec2(0.15, uSeasonT));
  float dens2 = fbm(cuv * 4.1 + 17.0);
  float cumulus = smoothstep(mix(0.5, 0.32, uCloud), 0.74, dens);
  cumulus = mix(cumulus, smoothstep(0.48, 0.8, dens2), 0.38);
  cumulus *= cumulusMask * mix(0.2, 1.0, 0.3 + uCloud * 0.7);

  float clouds = max(cirrus, cumulus);

  vec3 cloudBody = mix(vec3(0.22, 0.24, 0.32), vec3(0.86, 0.84, 0.88), 1.0 - uNightFactor * 0.55);
  cloudBody = mix(cloudBody, uAmber * 0.75, uTwilight * 0.4);
  cloudBody = mix(cloudBody, vec3(0.28, 0.24, 0.32), uCloud * 0.35);
  // Lit rim facing the sun — the Shinkai cloud edge
  float rim = pow(max(0.0, dot(dir, sunD)), 3.2);
  // v2: backlit cloud bodies sink cooler/darker so the amber rim pops
  cloudBody *= mix(0.62, 1.0, pow(max(0.0, dot(dir, sunD)), 1.4));
  vec3 cloudLit = mix(cloudBody, uSunColor * 1.35 + uAmber * 0.25, rim * (0.55 + uTwilight * 0.95));
  // Darker undersides
  cloudLit *= mix(0.72, 1.0, smoothstep(0.0, 0.45, elev) );
  col = mix(col, cloudLit, clouds);

  // Bright edge highlight on cloud tops
  float edge = smoothstep(0.52, 0.7, dens) * (1.0 - smoothstep(0.7, 0.88, dens));
  float edgeSun = 0.35 + 0.65 * pow(max(0.0, dot(dir, sunD)), 2.0);
  col += (uSunColor * 1.25 + uAmber * 0.45) * edge * cumulusMask * (0.35 + uTwilight * 1.15) * max(uSunIntensity, 0.35) * edgeSun;

  // Sun disc + large warm bloom / haze
  float sunDot = max(0.0, dot(dir, sunD));
  float disc = smoothstep(0.9982, 0.99985, sunDot);
  float glow = pow(sunDot, 28.0) * uSunIntensity;
  float haze = pow(sunDot, 5.0) * uSunIntensity * (0.18 + uTwilight * 0.55);
  col += uSunColor * (disc * 2.6 * uSunIntensity + glow * 0.85 + haze);
  col += uAmber * haze * uTwilight * 0.65;

  // Cheap crepuscular shafts (angular modulation + cloud occlusion)
  if (uGodray > 0.02 && sunDot > 0.15) {
    float ang = atan(dir.z - sunD.z, dir.x - sunD.x);
    float shafts = 0.0;
    for (int i = 0; i < 5; i++) {
      float fi = float(i);
      vec3 sd = normalize(mix(dir, sunD, 0.08 + fi * 0.07));
      float occ = fbm(vec2(atan(sd.z, sd.x) * 2.2, sd.y * 3.0) * 2.6);
      shafts += (1.0 - occ) * 0.2;
    }
    float radial = pow(sunDot, 3.5) * (0.55 + 0.45 * sin(ang * 14.0 + dens * 6.0));
    col += uSunColor * shafts * radial * uGodray * (0.18 + uTwilight * 0.28);
  }

  // Moon (opposite-ish, only at night)
  if (uNightFactor > 0.45 && elev > 0.12) {
    vec3 moonD = normalize(vec3(-sunD.x * 0.7, 0.55, -sunD.z * 0.55));
    float md = max(0.0, dot(dir, moonD));
    float moon = smoothstep(0.997, 0.9994, md);
    float moonHaze = pow(md, 80.0) * 0.35;
    col += vec3(0.85, 0.9, 1.0) * (moon * 1.1 + moonHaze) * uNightFactor * (1.0 - clouds * 0.7);
  }

  // Stars
  if (uNightFactor > 0.4 && elev > 0.14) {
    float n = hash(floor(dir.xz * 260.0 + dir.y * 80.0));
    float tw = 0.65 + 0.35 * sin(uTime * 1.7 + n * 40.0);
    float star = step(0.9972, n) * smoothstep(0.4, 0.92, uNightFactor) * (1.0 - clouds);
    col += vec3(0.9, 0.93, 1.0) * star * tw * (1.0 - uCloud * 0.65);
  }

  // Season hue
  float autumn = 1.0 - smoothstep(0.0, 0.22, abs(uSeasonT - 0.66));
  float spring = 1.0 - smoothstep(0.0, 0.22, abs(uSeasonT - 0.0));
  col.r += autumn * 0.04 * (1.0 - uNightFactor);
  col += uSakura * spring * 0.045 * sakuraBand;

  // Air-purple veil toward the horizon (not dirty grey)
  float fogAmt = exp(-max(elev, 0.0) * 6.5) * (0.16 + uFogDensity * 8.0);
  vec3 air = mix(uFogColor, uAirPurple, 0.55);
  col = mix(col, air, clamp(fogAmt, 0.0, 0.72));

  gl_FragColor = vec4(col, 1.0);
}
`;

export class SkyDome {
  readonly mesh: Mesh;
  readonly material: ShaderMaterial;

  constructor(radius = 120) {
    this.material = new ShaderMaterial({
      vertexShader: vert,
      fragmentShader: frag,
      uniforms: {
        uZenith: { value: new Color(Hex.deepIndigo) },
        uHorizon: { value: new Color(Hex.amberKey) },
        uSunDir: { value: new Vector3(0.55, 0.22, 0.4) },
        uSunColor: { value: new Color(0xffd2a0) },
        uSunIntensity: { value: 1 },
        uNightFactor: { value: 0.55 },
        uTwilight: { value: 0.85 },
        uCloud: { value: 0.7 },
        uSeasonT: { value: 0.66 },
        uFogColor: { value: new Color(Hex.airPurple) },
        uFogDensity: { value: 0.03 },
        uAmber: { value: new Color(Hex.amberKey) },
        uSakura: { value: new Color(Hex.sakuraBelt) },
        uAirPurple: { value: new Color(Hex.airPurple) },
        uGodray: { value: 0.5 },
        uTime: { value: 0 },
      },
      side: BackSide,
      depthWrite: false,
      fog: false,
    });
    this.mesh = new Mesh(new SphereGeometry(radius, 64, 32), this.material);
    this.mesh.name = 'sky_dome';
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -20;
  }

  apply(u: EnvUniformSnapshot, time = 0): void {
    this.material.uniforms.uZenith.value.setRGB(u.skyZenith[0], u.skyZenith[1], u.skyZenith[2]);
    this.material.uniforms.uHorizon.value.setRGB(u.skyHorizon[0], u.skyHorizon[1], u.skyHorizon[2]);
    this.material.uniforms.uSunDir.value.set(u.sunDir[0], u.sunDir[1], u.sunDir[2]);
    this.material.uniforms.uSunColor.value.setRGB(u.sunColor[0], u.sunColor[1], u.sunColor[2]);
    this.material.uniforms.uSunIntensity.value = u.sunIntensity;
    this.material.uniforms.uNightFactor.value = u.nightFactor;
    this.material.uniforms.uTwilight.value = u.twilight;
    this.material.uniforms.uCloud.value = u.cloudCover;
    this.material.uniforms.uSeasonT.value = u.seasonT;
    this.material.uniforms.uFogColor.value.setRGB(u.fogColor[0], u.fogColor[1], u.fogColor[2]);
    this.material.uniforms.uFogDensity.value = u.fogDensity;
    this.material.uniforms.uGodray.value = u.godray;
    this.material.uniforms.uTime.value = time;
  }

  dispose(): void {
    this.mesh.geometry.dispose();
    this.material.dispose();
  }
}
