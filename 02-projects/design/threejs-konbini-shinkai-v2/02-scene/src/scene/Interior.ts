import {
  BoxGeometry,
  Color,
  Group,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';
import { makeFloorTiles } from '../textures/makeTextures';
import { makeBento, makeBottle, makeCupNoodle, stockedShelf } from './Goods';

const W = 9.0;
const D = 7.0;
const H = 2.72;

/** Interior visible through the facade glass — readable product zones, cool white light. */
export class Interior {
  readonly group = new Group();
  private emissives: MeshStandardMaterial[] = [];
  private fridgeMat: MeshStandardMaterial;
  private ceilMats: MeshStandardMaterial[] = [];

  constructor() {
    this.group.name = 'interior';
    this.group.position.z = -D * 0.5 - 0.05;

    const floorMap = makeFloorTiles();
    const floor = new Mesh(
      new PlaneGeometry(W, D),
      new MeshStandardMaterial({
        map: floorMap,
        color: 0xe8e0d4,
        roughness: 0.42,
        metalness: 0.04,
      }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0.01;
    floor.receiveShadow = true;
    this.group.add(floor);

    const wallMat = new MeshStandardMaterial({
      color: 0xefe8dc,
      roughness: 0.82,
    });
    const back = new Mesh(new BoxGeometry(W + 0.1, H, 0.12), wallMat);
    back.position.set(0, H * 0.5, -D * 0.5);
    this.group.add(back);
    const left = new Mesh(new BoxGeometry(0.12, H, D), wallMat);
    left.position.set(-W * 0.5, H * 0.5, 0);
    this.group.add(left);
    const right = new Mesh(new BoxGeometry(0.12, H, D), wallMat);
    right.position.set(W * 0.5, H * 0.5, 0);
    this.group.add(right);

    const ceil = new Mesh(
      new PlaneGeometry(W, D),
      new MeshStandardMaterial({ color: 0xf4f6f8, roughness: 0.7 }),
    );
    ceil.rotation.x = Math.PI / 2;
    ceil.position.y = H;
    this.group.add(ceil);

    const cofferGeo = new BoxGeometry(1.15, 0.05, 0.55);
    for (const z of [-2.2, -0.4, 1.4, 2.35]) {
      for (const x of [-2.6, 0, 2.6]) {
        // Back = cooler cyan, front = warm checkout / sign bounce
        const back = z < -1;
        const front = z > 1;
        const emit = back ? 0xc8e8ea : front ? 0xffe6c0 : 0xf0f3f7;
        const mat = new MeshStandardMaterial({
          color: back ? 0xe8f2f2 : front ? 0xfff4e4 : 0xf4f6f8,
          emissive: new Color(emit),
          emissiveIntensity: back ? 1.55 : front ? 1.65 : 1.2,
          roughness: 0.35,
        });
        mat.userData.zone = back ? 'cool' : front ? 'warm' : 'mid';
        this.ceilMats.push(mat);
        this.emissives.push(mat);
        const m = new Mesh(cofferGeo, mat);
        m.position.set(x, H - 0.04, z);
        this.group.add(m);
        const frame = new Mesh(
          new BoxGeometry(1.28, 0.04, 0.68),
          new MeshStandardMaterial({ color: 0xd8dde2, roughness: 0.7 }),
        );
        frame.position.set(x, H - 0.02, z);
        this.group.add(frame);
      }
    }

    this.buildShelves();
    this.fridgeMat = this.buildCooler();
    this.buildCheckout();
    this.buildMagazine();
  }

  private buildShelves(): void {
    // Window-facing gondolas just inside the glass (local z ≈ 2.5 → world z ≈ -1)
    const onigiri = stockedShelf({ kind: 'onigiri', rows: 4, cols: 6, width: 1.55 });
    onigiri.position.set(-3.15, 0, 2.52);
    this.group.add(onigiri);

    // Window-facing bentos (tilted lids) next to the onigiri, still in the left glass
    const bento = stockedShelf({ kind: 'bento', rows: 3, cols: 4, width: 1.15 });
    bento.position.set(-1.85, 0, 2.5);
    this.group.add(bento);

    const bottles = stockedShelf({ kind: 'bottle', rows: 4, cols: 10, width: 1.8 });
    bottles.position.set(3.05, 0, 2.52);
    this.group.add(bottles);

    const cups = stockedShelf({ kind: 'cup', rows: 4, cols: 8, width: 1.45 });
    cups.position.set(3.35, 0, 1.7);
    this.group.add(cups);

    // Mid-store density, still readable if the camera glances past the door
    const midOnigiri = stockedShelf({ kind: 'onigiri', rows: 4, cols: 8, width: 1.6 });
    midOnigiri.position.set(-2.9, 0, 0.35);
    midOnigiri.rotation.y = Math.PI / 2;
    this.group.add(midOnigiri);

    const midBottle = stockedShelf({ kind: 'bottle', rows: 4, cols: 9, width: 1.6 });
    midBottle.position.set(2.9, 0, 0.35);
    midBottle.rotation.y = -Math.PI / 2;
    this.group.add(midBottle);

    const midCup = stockedShelf({ kind: 'cup', rows: 4, cols: 8, width: 1.5 });
    midCup.position.set(-1.0, 0, -1.15);
    this.group.add(midCup);

    const midBento = stockedShelf({ kind: 'bento', rows: 3, cols: 6, width: 1.5 });
    midBento.position.set(1.0, 0, -1.15);
    this.group.add(midBento);
  }

  private buildCooler(): MeshStandardMaterial {
    const body = new MeshStandardMaterial({
      color: 0xcfd4d8,
      roughness: 0.4,
      metalness: 0.35,
    });
    const frame = new MeshStandardMaterial({
      color: 0x2a3238,
      roughness: 0.4,
      metalness: 0.6,
    });
    const glass = new MeshStandardMaterial({
      color: 0xcfe8e8,
      emissive: new Color(Hex.fridgeCyan),
      emissiveIntensity: 0.28,
      roughness: 0.1,
      metalness: 0.12,
      transparent: true,
      opacity: 0.32,
    });
    this.emissives.push(glass);

    const z = -D * 0.5 + 0.38;
    const cooler = new Mesh(new BoxGeometry(6.6, 2.05, 0.7), body);
    cooler.position.set(0, 1.05, z);
    this.group.add(cooler);

    // Lit back panel so the cabinet reads as a cooler, not a grey box
    const backGlow = new MeshStandardMaterial({
      color: 0xe8f2f2,
      emissive: new Color(0xc8e8e6),
      emissiveIntensity: 0.7,
      roughness: 0.6,
    });
    this.emissives.push(backGlow);
    const glowPlane = new Mesh(new PlaneGeometry(6.3, 1.9), backGlow);
    glowPlane.position.set(0, 1.1, z + 0.2);
    this.group.add(glowPlane);

    for (let i = 0; i < 4; i++) {
      const x = -2.4 + i * 1.6;
      for (let row = 0; row < 4; row++) {
        for (let k = 0; k < 5; k++) {
          const b = makeBottle((i + row + k) % 5);
          b.position.set(x - 0.5 + k * 0.25, 0.28 + row * 0.42, z + 0.22);
          this.group.add(b);
        }
      }
      const f = new Mesh(new BoxGeometry(1.46, 1.82, 0.06), frame);
      f.position.set(x, 1.1, z + 0.36);
      this.group.add(f);
      const gl = new Mesh(new BoxGeometry(1.28, 1.64, 0.03), glass);
      gl.position.set(x, 1.1, z + 0.4);
      this.group.add(gl);
    }

    const strip = new MeshStandardMaterial({
      color: Hex.fridgeCyan,
      emissive: new Color(Hex.fridgeCyan),
      emissiveIntensity: 1.8,
    });
    this.emissives.push(strip);
    for (const x of [-3.25, 3.25]) {
      const s = new Mesh(new BoxGeometry(0.05, 1.9, 0.05), strip);
      s.position.set(x, 1.1, z + 0.38);
      this.group.add(s);
    }
    const top = new Mesh(new BoxGeometry(6.5, 0.05, 0.08), strip);
    top.position.set(0, 2.02, z + 0.36);
    this.group.add(top);
    return glass;
  }

  private buildCheckout(): void {
    const counter = new MeshStandardMaterial({
      color: 0x4a4240,
      roughness: 0.55,
    });
    const top = new MeshStandardMaterial({
      color: 0xe8e2d6,
      roughness: 0.4,
    });
    const isle = new Group();
    isle.position.set(0.95, 0, 2.38);
    isle.add(meshAt(new BoxGeometry(1.65, 0.92, 0.8), counter, 0, 0.46, 0));
    isle.add(meshAt(new BoxGeometry(1.68, 0.05, 0.84), top, 0, 0.94, 0));
    isle.add(meshAt(new BoxGeometry(0.32, 0.28, 0.28), counter, 0.55, 1.12, 0.1));
    const screen = new MeshStandardMaterial({
      color: 0x9ad0cc,
      emissive: new Color(0x6ec4c0),
      emissiveIntensity: 0.7,
      roughness: 0.25,
    });
    this.emissives.push(screen);
    isle.add(meshAt(new BoxGeometry(0.3, 0.22, 0.04), screen, 0.55, 1.38, 0.24));
    // A couple of bagged items on the counter so the register reads as a till
    const b1 = makeBento();
    b1.position.set(-0.45, 0.97, 0.05);
    isle.add(b1);
    const c1 = makeCupNoodle(0);
    c1.position.set(-0.18, 0.97, 0.12);
    isle.add(c1);
    this.group.add(isle);
  }

  private buildMagazine(): void {
    const rack = new MeshStandardMaterial({ color: 0x5a5048, roughness: 0.6 });
    const g = new Group();
    g.position.set(-3.85, 0, 2.15);
    g.add(meshAt(new BoxGeometry(0.7, 1.05, 0.28), rack, 0, 0.52, 0));
    const covers = [0xc43b3a, 0xf5f0e6, 0x3a5a78, 0xe8c878];
    for (let i = 0; i < 4; i++) {
      const m = new Mesh(
        new BoxGeometry(0.14, 0.2, 0.02),
        new MeshStandardMaterial({ color: covers[i], roughness: 0.55 }),
      );
      m.position.set(-0.24 + i * 0.16, 0.9, 0.15);
      g.add(m);
    }
    this.group.add(g);
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    for (const m of this.ceilMats) {
      const z = m.userData.zone as string;
      const base = z === 'cool' ? 1.5 : z === 'warm' ? 1.6 : 1.15;
      m.emissiveIntensity = base * u.interiorBoost;
    }
    this.fridgeMat.emissiveIntensity = 0.35 * u.emissiveBoost;
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

function meshAt(
  geo: BoxGeometry,
  mat: MeshStandardMaterial,
  x: number,
  y: number,
  z: number,
): Mesh {
  const m = new Mesh(geo, mat);
  m.position.set(x, y, z);
  return m;
}
