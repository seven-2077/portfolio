import {
  BoxGeometry,
  CatmullRomCurve3,
  Color,
  CylinderGeometry,
  Group,
  Mesh,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  SphereGeometry,
  TubeGeometry,
  Vector3,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';
import { makeNoren, makeVendingFront, makeNeighborWindows } from '../textures/makeTextures';

export class Props {
  readonly group = new Group();
  readonly glassMeshes: Mesh[] = [];
  private vendingBar: MeshStandardMaterial;
  private lampGlow: MeshStandardMaterial;
  private neighborWin: MeshStandardMaterial;
  private halo!: Mesh;

  constructor() {
    this.group.name = 'props';
    this.vendingBar = new MeshStandardMaterial({
      color: Hex.fridgeCyan,
      emissive: new Color(Hex.fridgeCyan),
      emissiveIntensity: 1.2,
    });
    this.lampGlow = new MeshStandardMaterial({
      color: Hex.amberKey,
      emissive: new Color(Hex.amberKey),
      emissiveIntensity: 2.2,
      transparent: true,
      opacity: 0.95,
    });
    this.neighborWin = new MeshStandardMaterial({
      map: makeNeighborWindows(),
      emissive: new Color(0xffd8a0),
      emissiveMap: makeNeighborWindows(),
      emissiveIntensity: 0.7,
      roughness: 0.6,
    });

    this.buildPoleAndWires();
    this.buildVending();
    this.buildBike();
    this.buildSign();
    this.buildLamp();
    this.buildGuardrail();
    this.buildPlanter();
  }

  private buildPoleAndWires(): void {
    const conc = new MeshStandardMaterial({
      color: 0x8a8680,
      roughness: 0.85,
    });
    const rust = new MeshStandardMaterial({
      color: 0x4a3a32,
      roughness: 0.55,
      metalness: 0.25,
    });
    const ins = new MeshStandardMaterial({
      color: 0xc8c0b0,
      roughness: 0.4,
    });

    // Left pole sits among the sakura, thinner and slightly receded so it does
    // not compete with the store. Right pole is a slim edge-of-frame anchor.
    const pole = new Mesh(new CylinderGeometry(0.055, 0.075, 6.8, 10), conc);
    pole.position.set(-8.8, 3.4, 2.55);
    pole.castShadow = true;
    this.group.add(pole);

    const arm = new Mesh(new BoxGeometry(1.8, 0.05, 0.07), rust);
    arm.position.set(-8.8, 6.15, 2.55);
    this.group.add(arm);
    for (const x of [-9.5, -9.05, -8.55, -8.1]) {
      const i = new Mesh(new CylinderGeometry(0.028, 0.035, 0.12, 8), ins);
      i.position.set(x, 6.1, 2.55);
      this.group.add(i);
    }
    const box = new Mesh(new BoxGeometry(0.28, 0.38, 0.22), rust);
    box.position.set(-8.8, 5.15, 2.72);
    this.group.add(box);

    const wireMat = new MeshStandardMaterial({
      color: 0x2a2a2c,
      roughness: 0.55,
      metalness: 0.35,
    });
    const spans: Array<[Vector3, Vector3, number]> = [
      [new Vector3(-9.5, 6.1, 2.55), new Vector3(13.0, 5.85, 9.15), 0.7],
      [new Vector3(-9.05, 6.1, 2.55), new Vector3(13.3, 5.8, 9.4), 0.78],
      [new Vector3(-8.55, 6.1, 2.55), new Vector3(-16.5, 6.05, -5.2), 0.45],
      [new Vector3(-8.1, 6.1, 2.55), new Vector3(-16.0, 5.95, -5.5), 0.5],
    ];
    for (const [a, b, sag] of spans) {
      this.group.add(wire(a, b, sag, wireMat));
    }

    const pole2 = new Mesh(new CylinderGeometry(0.045, 0.06, 6.2, 10), conc);
    pole2.position.set(13.2, 3.1, 9.2);
    pole2.castShadow = true;
    this.group.add(pole2);
    const arm2 = new Mesh(new BoxGeometry(1.2, 0.045, 0.055), rust);
    arm2.position.set(13.2, 5.8, 9.2);
    this.group.add(arm2);
  }

  private buildVending(): void {
    const body = new MeshStandardMaterial({
      color: 0x161c22,
      roughness: 0.22,
      metalness: 0.38,
    });
    const g = new Group();
    g.position.set(-4.55, 0, 1.15);
    const husk = new Mesh(new BoxGeometry(0.78, 1.82, 0.62), body);
    husk.position.y = 0.91;
    husk.castShadow = true;
    g.add(husk);
    // slight rounding via extra plates is skipped; glass front + top bar carry the look
    const front = new Mesh(
      new PlaneGeometry(0.68, 1.62),
      new MeshStandardMaterial({
        map: makeVendingFront(),
        roughness: 0.22,
        metalness: 0.16,
      }),
    );
    front.position.set(0, 0.95, 0.315);
    g.add(front);

    const glass = new MeshPhysicalMaterial({
      color: 0xa8d4d0,
      metalness: 0.1,
      roughness: 0.08,
      transmission: 0.35,
      transparent: true,
      opacity: 0.55,
      envMapIntensity: 1.1,
    });
    const pane = new Mesh(new BoxGeometry(0.66, 1.15, 0.02), glass);
    pane.position.set(0, 1.12, 0.322);
    g.add(pane);
    this.glassMeshes.push(pane);

    const bar = new Mesh(new BoxGeometry(0.7, 0.06, 0.08), this.vendingBar);
    bar.position.set(0, 1.8, 0.3);
    g.add(bar);
    const wet = new Mesh(
      new PlaneGeometry(0.95, 0.7),
      new MeshStandardMaterial({
        color: 0x1a1c1e,
        roughness: 0.08,
        metalness: 0.65,
        transparent: true,
        opacity: 0.55,
      }),
    );
    wet.rotation.x = -Math.PI / 2;
    wet.position.set(0, 0.012, 0.1);
    g.add(wet);
    this.group.add(g);
  }

  private buildBike(): void {
    const paint = new MeshStandardMaterial({
      color: 0x243240,
      roughness: 0.22,
      metalness: 0.52,
    });
    const rubber = new MeshStandardMaterial({
      color: 0x161616,
      roughness: 0.42,
    });
    const g = new Group();
    g.position.set(4.7, 0, 1.35);
    g.rotation.y = -0.4;
    const wheel = (x: number) => {
      const t = new Mesh(new CylinderGeometry(0.28, 0.28, 0.04, 18, 1, true), rubber);
      t.rotation.z = Math.PI / 2;
      t.position.set(x, 0.28, 0);
      const hub = new Mesh(new CylinderGeometry(0.04, 0.04, 0.05, 8), paint);
      hub.rotation.z = Math.PI / 2;
      hub.position.set(x, 0.28, 0);
      g.add(t, hub);
    };
    wheel(-0.42);
    wheel(0.42);
    // frame diamond
    const tube = (a: Vector3, b: Vector3) => {
      const dir = b.clone().sub(a);
      const len = dir.length();
      const m = new Mesh(new CylinderGeometry(0.015, 0.015, len, 6), paint);
      m.position.copy(a.clone().add(b).multiplyScalar(0.5));
      m.quaternion.setFromUnitVectors(new Vector3(0, 1, 0), dir.normalize());
      g.add(m);
    };
    tube(new Vector3(-0.42, 0.28, 0), new Vector3(0.05, 0.72, 0));
    tube(new Vector3(0.05, 0.72, 0), new Vector3(0.42, 0.28, 0));
    tube(new Vector3(-0.42, 0.28, 0), new Vector3(-0.05, 0.52, 0));
    tube(new Vector3(-0.05, 0.52, 0), new Vector3(0.42, 0.28, 0));
    tube(new Vector3(0.05, 0.72, 0), new Vector3(0.05, 0.86, 0));
    const bar = new Mesh(new CylinderGeometry(0.012, 0.012, 0.42, 6), paint);
    bar.rotation.z = Math.PI / 2;
    bar.position.set(0.05, 0.86, 0);
    g.add(bar);
    const seat = new Mesh(new BoxGeometry(0.16, 0.03, 0.08), rubber);
    seat.position.set(-0.08, 0.74, 0);
    g.add(seat);
    const drip = new Mesh(
      new PlaneGeometry(1.15, 0.45),
      new MeshStandardMaterial({
        color: 0x1a1c1e,
        roughness: 0.1,
        metalness: 0.55,
        transparent: true,
        opacity: 0.4,
      }),
    );
    drip.rotation.x = -Math.PI / 2;
    drip.position.set(0, 0.01, 0);
    g.add(drip);
    this.group.add(g);
  }

  private buildSign(): void {
    const post = new Mesh(
      new CylinderGeometry(0.028, 0.032, 2.1, 8),
      new MeshStandardMaterial({ color: 0x4a4e52, roughness: 0.4, metalness: 0.5 }),
    );
    post.position.set(7.4, 1.05, 2.4);
    this.group.add(post);
    const board = new Mesh(
      new BoxGeometry(0.55, 0.7, 0.035),
      new MeshStandardMaterial({ color: 0xf5f0e6, roughness: 0.5 }),
    );
    board.position.set(7.4, 1.95, 2.4);
    this.group.add(board);
    const accent = new Mesh(
      new BoxGeometry(0.55, 0.06, 0.04),
      new MeshStandardMaterial({
        color: Hex.sakuraBelt,
        emissive: new Color(Hex.sakuraBelt),
        emissiveIntensity: 0.15,
      }),
    );
    accent.position.set(7.4, 2.34, 2.4);
    this.group.add(accent);
  }

  private buildLamp(): void {
    // Slim street lamp pushed to the right edge — a presence, not a silhouette hero.
    const metal = new MeshStandardMaterial({
      color: 0x6a6e74,
      roughness: 0.5,
      metalness: 0.45,
    });
    const pole = new Mesh(new CylinderGeometry(0.032, 0.045, 3.7, 10), metal);
    pole.position.set(11.2, 1.85, 8.4);
    pole.castShadow = true;
    this.group.add(pole);
    const pts = [
      new Vector3(11.2, 3.68, 8.4),
      new Vector3(11.2, 3.92, 8.15),
      new Vector3(10.85, 3.95, 7.85),
    ];
    const curve = new CatmullRomCurve3(pts);
    const arm = new Mesh(new TubeGeometry(curve, 12, 0.02, 6, false), metal);
    this.group.add(arm);
    const lamp = new Mesh(new SphereGeometry(0.07, 12, 10), this.lampGlow);
    lamp.position.set(10.85, 3.88, 7.82);
    this.group.add(lamp);

    this.halo = new Mesh(
      new SphereGeometry(0.14, 16, 12),
      new MeshStandardMaterial({
        color: Hex.amberKey,
        emissive: new Color(Hex.amberKey),
        emissiveIntensity: 0.5,
        transparent: true,
        opacity: 0.06,
        depthWrite: false,
      }),
    );
    this.halo.position.copy(lamp.position);
    this.group.add(this.halo);
  }

  private buildGuardrail(): void {
    const steel = new MeshStandardMaterial({
      color: 0xb8b0a4,
      roughness: 0.4,
      metalness: 0.45,
    });
    for (let i = 0; i < 6; i++) {
      const x = 2.8 + i * 0.85;
      const p = new Mesh(new CylinderGeometry(0.03, 0.03, 0.55, 8), steel);
      p.position.set(x, 0.35, 2.52);
      this.group.add(p);
    }
    const rail = new Mesh(new BoxGeometry(5.1, 0.04, 0.05), steel);
    rail.position.set(4.9, 0.55, 2.52);
    this.group.add(rail);
    const rail2 = new Mesh(new BoxGeometry(5.1, 0.04, 0.05), steel);
    rail2.position.set(4.9, 0.32, 2.52);
    this.group.add(rail2);
  }

  /** v2 single-store composition: neighbour eatery removed from the frame (kept for reference). */
  buildNeighborLegacy(): void {
    const plaster = new MeshStandardMaterial({
      color: 0x6a5e52,
      roughness: 0.85,
    });
    const b = new Mesh(new BoxGeometry(6.5, 6.8, 5.5), plaster);
    b.position.set(-12.2, 3.4, -2.2);
    b.castShadow = true;
    this.group.add(b);
    const face = new Mesh(new PlaneGeometry(6.3, 6.5), this.neighborWin);
    face.position.set(-8.92, 3.4, -2.2);
    face.rotation.y = Math.PI / 2;
    this.group.add(face);

    // Noren of a small eatery at ground
    const noren = new Mesh(
      new PlaneGeometry(1.8, 1.05),
      new MeshStandardMaterial({
        map: makeNoren(),
        roughness: 0.7,
        transparent: true,
      }),
    );
    noren.position.set(-8.9, 1.55, -0.4);
    noren.rotation.y = Math.PI / 2;
    this.group.add(noren);

    // Warm entrance glow plane
    const glow = new Mesh(
      new PlaneGeometry(1.4, 1.6),
      new MeshStandardMaterial({
        color: 0xffd8a0,
        emissive: new Color(0xffc878),
        emissiveIntensity: 0.8,
        transparent: true,
        opacity: 0.85,
      }),
    );
    glow.position.set(-8.94, 1.1, -0.4);
    glow.rotation.y = Math.PI / 2;
    this.group.add(glow);
  }

  private buildPlanter(): void {
    const pot = new Mesh(
      new CylinderGeometry(0.22, 0.18, 0.32, 10),
      new MeshStandardMaterial({ color: 0x5a4034, roughness: 0.7 }),
    );
    pot.position.set(3.6, 0.22, 0.7);
    this.group.add(pot);
    const leaf = new MeshStandardMaterial({ color: 0x3a5a38, roughness: 0.7 });
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * Math.PI * 2;
      const l = new Mesh(new SphereGeometry(0.16, 8, 6), leaf);
      l.scale.set(1, 0.7, 0.6);
      l.position.set(3.6 + Math.cos(a) * 0.12, 0.48, 0.7 + Math.sin(a) * 0.12);
      this.group.add(l);
    }
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    this.vendingBar.emissiveIntensity = 0.8 + u.emissiveBoost * 0.7;
    this.lampGlow.emissiveIntensity = 0.7 * u.streetLampBoost;
    this.neighborWin.emissiveIntensity = 0.45 + u.nightFactor * 0.7 + u.twilight * 0.2;
    const haloMat = this.halo.material as MeshStandardMaterial;
    haloMat.opacity = 0.05 + u.streetLampBoost * 0.03;
    haloMat.emissiveIntensity = 0.5 * u.streetLampBoost;
  }

  setEnvMap(envMap: MeshPhysicalMaterial['envMap']): void {
    for (const m of this.glassMeshes) {
      const mat = m.material as MeshPhysicalMaterial;
      mat.envMap = envMap;
      mat.needsUpdate = true;
    }
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

function wire(
  a: Vector3,
  b: Vector3,
  sag: number,
  mat: MeshStandardMaterial,
): Mesh {
  const pts: Vector3[] = [];
  for (let i = 0; i <= 18; i++) {
    const t = i / 18;
    const p = a.clone().lerp(b, t);
    p.y -= sag * 4 * t * (1 - t);
    pts.push(p);
  }
  const curve = new CatmullRomCurve3(pts);
  const mesh = new Mesh(new TubeGeometry(curve, 18, 0.007, 5, false), mat);
  mesh.castShadow = true;
  return mesh;
}
