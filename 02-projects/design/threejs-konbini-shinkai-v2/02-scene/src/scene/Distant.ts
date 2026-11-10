import {
  BoxGeometry,
  Color,
  ConeGeometry,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  Shape,
  ShapeGeometry,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';

/**
 * v2 distant layer — no city block. Two ridge silhouettes tinted by aerial
 * perspective (blue-violet grey) plus a handful of low houses beyond the
 * railway, each with at most one warm window. Supporting role only.
 */
export class Distant {
  readonly group = new Group();
  private ridgeMats: MeshBasicMaterial[] = [];
  private ridgeBase: Color[] = [];
  private houseMat: MeshStandardMaterial;
  private winMat: MeshStandardMaterial;

  constructor() {
    this.group.name = 'distant';

    // Ridge silhouettes — unlit, coloured each frame toward fog/air purple
    const ridges: Array<[number, number, number, number, number]> = [
      // z, baseHeight, amplitude, seed, colour
      [-95, 6, 5, 3, 0x5a6580],
      [-140, 10, 7, 9, 0x7a84a0],
    ];
    for (const [z, base, amp, seed, col] of ridges) {
      const shape = new Shape();
      const w = 360;
      shape.moveTo(-w / 2, -2);
      for (let i = 0; i <= 120; i++) {
        const x = -w / 2 + (i / 120) * w;
        const y =
          base +
          Math.sin(x * 0.021 + seed) * amp * 0.55 +
          Math.sin(x * 0.057 + seed * 2.3) * amp * 0.3 +
          Math.sin(x * 0.13 + seed * 0.7) * amp * 0.12;
        shape.lineTo(x, y);
      }
      shape.lineTo(w / 2, -2);
      shape.lineTo(-w / 2, -2);
      const mat = new MeshBasicMaterial({ color: col, fog: false });
      this.ridgeMats.push(mat);
      this.ridgeBase.push(new Color(col));
      const m = new Mesh(new ShapeGeometry(shape), mat);
      m.position.set(0, 0, z);
      m.renderOrder = -10;
      this.group.add(m);
    }

    // Sparse low houses past the railway (behind the embankment)
    this.houseMat = new MeshStandardMaterial({
      color: 0x3a4258,
      roughness: 0.9,
      emissive: new Color(Hex.airPurple),
      emissiveIntensity: 0.08,
    });
    this.winMat = new MeshStandardMaterial({
      color: 0xffd8a8,
      emissive: new Color(0xffc878),
      emissiveIntensity: 0.6,
    });
    const houses: Array<[number, number, number, number]> = [
      // x, z, width, rotY — past the railway, supporting silhouettes only
      [-38, -62, 5, 0.1],
      [-8, -70, 4.2, -0.12],
      [30, -64, 5.2, 0.18],
      [52, -74, 4.4, 0],
    ];
    houses.forEach(([x, z, w, ry], i) => {
      const g = new Group();
      g.position.set(x, 0, z);
      g.rotation.y = ry;
      const body = new Mesh(new BoxGeometry(w, 3.2, 4.5), this.houseMat);
      body.position.y = 1.6;
      g.add(body);
      const roof = new Mesh(new ConeGeometry(w * 0.78, 1.6, 4, 1), this.houseMat);
      roof.rotation.y = Math.PI / 4;
      roof.scale.set(1, 1, 0.72);
      roof.position.y = 4.0;
      g.add(roof);
      if (i !== 3) {
        const win = new Mesh(new PlaneGeometry(0.7, 0.55), this.winMat);
        win.position.set((i % 2 ? -1 : 1) * w * 0.2, 1.9, 2.26);
        g.add(win);
      }
      this.group.add(g);
    });
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    // Aerial perspective: blend ridges toward fog colour; farther = more veiled
    const fog = new Color().setRGB(u.fogColor[0], u.fogColor[1], u.fogColor[2]);
    const horizon = new Color().setRGB(u.skyHorizon[0], u.skyHorizon[1], u.skyHorizon[2]);
    const veil = fog.clone().lerp(horizon, 0.25);
    this.ridgeMats.forEach((m, i) => {
      const base = this.ridgeBase[i]!.clone();
      const dark = 1 - u.nightFactor * 0.55;
      base.multiplyScalar(dark);
      m.color.copy(base).lerp(veil, i === 0 ? 0.58 : 0.78);
    });
    this.houseMat.emissiveIntensity = 0.05 + u.fogDensity * 2.5;
    this.winMat.emissiveIntensity = 0.3 + u.nightFactor * 0.9 + u.twilight * 0.25;
  }

  dispose(): void {
    this.group.traverse((o) => {
      if (o instanceof Mesh) {
        o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) m.dispose();
      }
    });
  }
}
