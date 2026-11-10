import {
  BoxGeometry,
  Color,
  CylinderGeometry,
  ExtrudeGeometry,
  Group,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  Shape,
  type Texture,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';
import { makeSidewalk } from '../textures/makeTextures';
import { applyWetRoad, createWetRoad, setWetRoadSignMap } from '../shaders/wetRoad';
import type { Reflector } from 'three/addons/objects/Reflector.js';

export class Street {
  readonly group = new Group();
  readonly road: Reflector;
  private tactileMat: MeshStandardMaterial;
  private puddles: Mesh[] = [];
  private puddleMat: MeshStandardMaterial;

  constructor() {
    this.group.name = 'street';

    this.road = createWetRoad(46, 22);
    this.road.position.set(0, 0.0, 13.4);
    this.group.add(this.road);

    const walkMap = makeSidewalk();
    const walkMat = new MeshStandardMaterial({
      map: walkMap,
      color: 0x8a8680,
      roughness: 0.72,
      metalness: 0.04,
    });
    const walk = new Mesh(new PlaneGeometry(28, 2.55), walkMat);
    walk.rotation.x = -Math.PI / 2;
    walk.position.set(0, 0.045, 1.15);
    walk.receiveShadow = true;
    this.group.add(walk);

    // Curb
    const curbMat = new MeshStandardMaterial({
      color: 0xb8b2a8,
      roughness: 0.6,
    });
    const curb = new Mesh(new BoxGeometry(28, 0.14, 0.22), curbMat);
    curb.position.set(0, 0.07, 2.38);
    curb.castShadow = true;
    this.group.add(curb);

    // Yellow tactile paving
    this.tactileMat = new MeshStandardMaterial({
      color: 0xd2b84a,
      roughness: 0.55,
    });
    const tact = new Mesh(new BoxGeometry(6.5, 0.02, 0.32), this.tactileMat);
    tact.position.set(0, 0.06, 0.55);
    this.group.add(tact);
    // bumps
    const bump = new CylinderGeometry(0.03, 0.03, 0.02, 8);
    for (let i = 0; i < 18; i++) {
      for (let j = 0; j < 2; j++) {
        const b = new Mesh(bump, this.tactileMat);
        b.position.set(-3 + i * 0.35, 0.075, 0.45 + j * 0.2);
        this.group.add(b);
      }
    }

    // Lane dash
    const paint = new MeshStandardMaterial({
      color: 0xc8c0a8,
      roughness: 0.55,
      emissive: new Color(0x332e20),
      emissiveIntensity: 0.15,
    });
    for (let i = 0; i < 8; i++) {
      const d = new Mesh(new BoxGeometry(0.12, 0.005, 1.1), paint);
      d.position.set(0.15, 0.012, 4.2 + i * 2.1);
      this.group.add(d);
    }

    // Manhole
    const hole = new Mesh(
      new CylinderGeometry(0.32, 0.32, 0.03, 20),
      new MeshStandardMaterial({ color: 0x3a3e42, roughness: 0.45, metalness: 0.4 }),
    );
    hole.position.set(2.4, 0.02, 3.6);
    this.group.add(hole);

    // Drain at curb
    const drain = new Mesh(
      new BoxGeometry(0.7, 0.04, 0.18),
      new MeshStandardMaterial({ color: 0x2a2c2e, roughness: 0.5, metalness: 0.4 }),
    );
    drain.position.set(-1.6, 0.04, 2.38);
    this.group.add(drain);

    this.puddleMat = new MeshStandardMaterial({
      color: Hex.wetBlack,
      roughness: 0.05,
      metalness: 0.85,
      transparent: true,
      opacity: 0.85,
    });
    this.puddles = this.makePuddles().map((m) => {
      m.visible = false;
      this.group.add(m);
      return m;
    });
  }

  private makePuddles(): Mesh[] {
    const mats = this.puddleMat;
    const blobs: Array<[number, number, number, number]> = [
      [1.2, 3.4, 1.6, 0.7],
      [-2.4, 4.1, 1.1, 0.55],
      [3.6, 5.5, 0.9, 0.45],
      [-0.4, 6.8, 1.8, 0.6],
    ];
    return blobs.map(([x, z, w, d], i) => {
      const shape = new Shape();
      const steps = 18;
      for (let k = 0; k <= steps; k++) {
        const a = (k / steps) * Math.PI * 2;
        const rx = w * 0.5 * (0.82 + 0.18 * Math.sin(a * 3.0 + i));
        const rz = d * 0.5 * (0.8 + 0.2 * Math.cos(a * 2.0 + i * 1.7));
        const px = Math.cos(a) * rx;
        const pz = Math.sin(a) * rz;
        if (k === 0) shape.moveTo(px, pz);
        else shape.lineTo(px, pz);
      }
      const geo = new ExtrudeGeometry(shape, { depth: 0.012, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2);
      const m = new Mesh(geo, mats);
      m.position.set(x, 0.016, z);
      m.name = `puddle_${i}`;
      return m;
    });
  }

  setSignMap(map: Texture | null): void {
    setWetRoadSignMap(this.road, map);
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    applyWetRoad(this.road, u);
    this.puddleMat.opacity = Math.min(1, Math.max(0, (u.wetness - 0.12) * 1.15));
    this.puddleMat.roughness = 0.04;
    for (const p of this.puddles) p.visible = false;
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
