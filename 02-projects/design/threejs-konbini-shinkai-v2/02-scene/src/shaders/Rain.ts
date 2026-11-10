import {
  AdditiveBlending,
  BufferGeometry,
  Color,
  Float32BufferAttribute,
  Points,
  ShaderMaterial,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';

const vert = /* glsl */ `
uniform float uTime;
uniform float uAmount;
attribute float aSeed;
attribute float aLen;
varying float vAlpha;
void main() {
  vec3 p = position;
  float fall = mod(uTime * (7.0 + aSeed * 5.0) + aSeed * 30.0, 16.0);
  p.y = 8.5 - fall;
  p.x += sin(aSeed * 20.0) * 0.04;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = aLen * (36.0 / max(1.2, -mv.z));
  vAlpha = uAmount * 0.28;
}
`;

const frag = /* glsl */ `
precision highp float;
uniform vec3 uColor;
varying float vAlpha;
void main() {
  vec2 uv = gl_PointCoord - vec2(0.5, 0.5);
  // vertical streak
  float s = 1.0 - smoothstep(0.02, 0.11, abs(uv.x));
  s *= 1.0 - smoothstep(0.42, 0.5, abs(uv.y));
  if (s < 0.08) discard;
  gl_FragColor = vec4(uColor, s * vAlpha);
}
`;

export class Rain {
  readonly points: Points;
  private mat: ShaderMaterial;

  constructor(count = 900) {
    const pos: number[] = [];
    const seed: number[] = [];
    const len: number[] = [];
    for (let i = 0; i < count; i++) {
      pos.push((Math.random() - 0.5) * 28, Math.random() * 16, (Math.random() - 0.3) * 24);
      seed.push(Math.random());
      len.push(0.7 + Math.random() * 1.1);
    }
    const geo = new BufferGeometry();
    geo.setAttribute('position', new Float32BufferAttribute(pos, 3));
    geo.setAttribute('aSeed', new Float32BufferAttribute(seed, 1));
    geo.setAttribute('aLen', new Float32BufferAttribute(len, 1));
    this.mat = new ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uAmount: { value: 0 },
        uColor: { value: new Color(0xc8d0dc) },
      },
      vertexShader: vert,
      fragmentShader: frag,
      transparent: true,
      depthWrite: false,
      fog: false,
      blending: AdditiveBlending,
    });
    this.points = new Points(geo, this.mat);
    this.points.name = 'rain';
    this.points.frustumCulled = false;
  }

  apply(u: EnvUniformSnapshot, _dt: number, elapsed: number): void {
    this.mat.uniforms.uTime.value = elapsed;
    this.mat.uniforms.uAmount.value = u.weather === 'rain' ? 1 : u.weather === 'overcast' ? 0.08 : 0;
    this.points.visible = (this.mat.uniforms.uAmount.value as number) > 0.04;
  }

  dispose(): void {
    this.points.geometry.dispose();
    this.mat.dispose();
  }
}
