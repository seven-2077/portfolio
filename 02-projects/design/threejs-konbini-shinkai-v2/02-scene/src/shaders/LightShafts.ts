import {
  AdditiveBlending,
  Camera,
  CanvasTexture,
  Color,
  DoubleSide,
  Group,
  Matrix4,
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  Vector3,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';

/**
 * In-scene crepuscular shafts: additive planes along the sun axis,
 * depth-tested so they thread through sakura gaps and past the store
 * instead of sitting as a sky decoration.
 */
function shaftTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 64;
  c.height = 256;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  const grd = g.createLinearGradient(0, 0, 64, 0);
  grd.addColorStop(0, 'rgba(255,230,200,0)');
  grd.addColorStop(0.45, 'rgba(255,230,200,0.85)');
  grd.addColorStop(0.55, 'rgba(255,236,210,1)');
  grd.addColorStop(0.55, 'rgba(255,230,200,0.85)');
  grd.addColorStop(1, 'rgba(255,230,200,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 256);
  const t = new CanvasTexture(c);
  t.needsUpdate = true;
  return t;
}

const vert = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const frag = /* glsl */ `
uniform sampler2D uMap;
uniform vec3 uColor;
uniform float uOpacity;
varying vec2 vUv;
void main() {
  float a = texture2D(uMap, vUv).a * uOpacity;
  a *= smoothstep(0.0, 0.14, vUv.x) * smoothstep(1.0, 0.86, vUv.x);
  a *= smoothstep(0.0, 0.08, vUv.y) * smoothstep(1.0, 0.62, vUv.y);
  if (a < 0.004) discard;
  gl_FragColor = vec4(uColor, a);
}
`;

export class LightShafts {
  readonly group = new Group();
  private shafts: Mesh[] = [];
  private mats: ShaderMaterial[] = [];
  private tex: CanvasTexture;

  constructor() {
    this.group.name = 'light_shafts';
    this.tex = shaftTexture();
    const widths = [3.6, 2.2, 2.8, 1.6, 2.4, 1.4, 3.0];
    const lengths = [96, 88, 100, 80, 92, 78, 90];
    for (let i = 0; i < 7; i++) {
      const mat = new ShaderMaterial({
        uniforms: {
          uMap: { value: this.tex },
          uColor: { value: new Color(0xffc888) },
          uOpacity: { value: 0 },
        },
        vertexShader: vert,
        fragmentShader: frag,
        transparent: true,
        depthWrite: false,
        depthTest: true,
        blending: AdditiveBlending,
        side: DoubleSide,
        fog: false,
      });
      const mesh = new Mesh(new PlaneGeometry(widths[i], lengths[i], 1, 1), mat);
      mesh.frustumCulled = false;
      mesh.renderOrder = 2;
      this.group.add(mesh);
      this.shafts.push(mesh);
      this.mats.push(mat);
    }
  }

  apply(u: EnvUniformSnapshot, camera: Camera): void {
    const dir = new Vector3(u.sunDir[0], u.sunDir[1], u.sunDir[2]).normalize();
    const focus = new Vector3(-5.2, 4.6, 3.2);
    const far = focus.clone().addScaledVector(dir, 58);
    const near = focus.clone().addScaledVector(dir, -22);
    const mid = far.clone().lerp(near, 0.48);
    const toCam = camera.position.clone().sub(mid);
    const opacity = Math.max(0, u.godray) * (0.28 + u.twilight * 0.32);
    const color = new Color().setRGB(
      Math.min(1, u.sunColor[0] * 1.15 + 0.08),
      Math.min(1, u.sunColor[1] * 1.05 + 0.04),
      Math.min(1, u.sunColor[2] * 0.9),
    );

    const xAxis = new Vector3();
    const yAxis = new Vector3();
    const zAxis = new Vector3();
    const basis = new Matrix4();

    for (let i = 0; i < this.shafts.length; i++) {
      const mesh = this.shafts[i]!;
      const mat = this.mats[i]!;
      const lateral = (i - 3) * 0.7;
      const lift = (i % 3) * 0.25 - 0.2;
      yAxis.copy(dir);
      zAxis.copy(toCam);
      // keep shaft facing the camera while staying aligned to the sun axis
      xAxis.crossVectors(yAxis, zAxis);
      if (xAxis.lengthSq() < 1e-6) xAxis.set(1, 0, 0);
      else xAxis.normalize();
      zAxis.crossVectors(xAxis, yAxis).normalize();
      basis.makeBasis(xAxis, yAxis, zAxis);
      mesh.quaternion.setFromRotationMatrix(basis);
      mesh.position.copy(mid).addScaledVector(xAxis, lateral).addScaledVector(zAxis, lift);
      mat.uniforms.uOpacity.value = opacity * (0.75 + (i % 3) * 0.12);
      (mat.uniforms.uColor.value as Color).copy(color);
    }
  }

  dispose(): void {
    this.tex.dispose();
    for (const m of this.shafts) {
      m.geometry.dispose();
      (m.material as ShaderMaterial).dispose();
    }
  }
}
