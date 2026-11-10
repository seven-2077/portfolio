import {
  ACESFilmicToneMapping,
  Color,
  CubeCamera,
  FogExp2,
  HalfFloatType,
  PerspectiveCamera,
  PMREMGenerator,
  Scene,
  SRGBColorSpace,
  WebGLCubeRenderTarget,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { Environment } from '../env/Environment';
import { SkyDome } from '../shaders/SkyDome';
import { Rain } from '../shaders/Rain';
import { Facade } from './Facade';
import { Interior } from './Interior';
import { Street } from './Street';
import { Props } from './Props';
import { Distant } from './Distant';
import { Nature } from './Nature';
import { Lights } from './Lights';
import { Mist } from '../shaders/Mist';

export class World {
  readonly scene = new Scene();
  readonly camera: PerspectiveCamera;
  readonly renderer: WebGLRenderer;
  readonly controls: OrbitControls;

  private env: Environment;
  private host: HTMLElement;
  private sky: SkyDome;
  private rain: Rain;
  private facade: Facade;
  private interior: Interior;
  private street: Street;
  private props: Props;
  private distant: Distant;
  private nature: Nature;
  private lastDt = 0;
  private lights: Lights;
  private mist: Mist;
  private cubeRT: WebGLCubeRenderTarget;
  private cubeCam: CubeCamera;
  private pmrem: PMREMGenerator;
  private envReady = false;
  private raf = 0;
  private running = false;
  private lastT = 0;
  private elapsed = 0;

  constructor(host: HTMLElement, env: Environment) {
    this.host = host;
    this.env = env;

    this.scene.background = new Color(0x0e1a32);
    this.scene.fog = new FogExp2(0x6b7ba8, 0.025);

    // Shot 1 establishing: low 3/4, plenty of sky, store as the visual centre
    this.camera = new PerspectiveCamera(40, 1, 0.1, 400);
    this.camera.position.set(5.6, 1.22, 16.8);

    this.renderer = new WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(-0.2, 2.62, -0.6);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minPolarAngle = 0.18;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.minDistance = 3;
    this.controls.maxDistance = 34;
    this.controls.update();

    this.sky = new SkyDome(140);
    this.scene.add(this.sky.mesh);

    this.interior = new Interior();
    this.scene.add(this.interior.group);

    this.facade = new Facade();
    this.scene.add(this.facade.group);

    this.street = new Street();
    this.street.setSignMap(this.facade.signMap);
    this.scene.add(this.street.group);

    this.props = new Props();
    this.scene.add(this.props.group);

    this.distant = new Distant();
    this.scene.add(this.distant.group);

    this.nature = new Nature();
    this.scene.add(this.nature.group);

    this.lights = new Lights();
    this.scene.add(this.lights.group);
    this.lights.attachFog(this.scene);
    this.lights.enableShadows(this.renderer);

    this.mist = new Mist();
    this.scene.add(this.mist.group);

    this.rain = new Rain(420);
    this.scene.add(this.rain.points);

    this.cubeRT = new WebGLCubeRenderTarget(1024, { type: HalfFloatType });
    this.cubeCam = new CubeCamera(0.25, 160, this.cubeRT);
    this.cubeCam.position.set(0.15, 1.9, 2.15);
    this.scene.add(this.cubeCam);
    this.pmrem = new PMREMGenerator(this.renderer);

    const u0 = this.env.update(0);
    this.applyEnv(u0, 0);

    this.onResize = this.onResize.bind(this);
    window.addEventListener('resize', this.onResize);
    this.onResize();
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.lastT = performance.now();
    const tick = (now: number) => {
      this.raf = requestAnimationFrame(tick);
      const dt = Math.min(0.05, (now - this.lastT) / 1000);
      this.lastT = now;
      this.elapsed += dt;
      this.lastDt = dt;

      const u = this.env.update(dt);
      this.applyEnv(u, this.elapsed);
      this.controls.update();

      if (!this.envReady) {
        this.captureEnvironment();
        this.envReady = true;
      }

      this.renderer.render(this.scene, this.camera);
    };
    tick(performance.now());
  }

  private captureEnvironment(): void {
    // Hide transmissive / reflective surfaces to avoid feedback, capture sky + store lights
    const hidden: Array<{ obj: { visible: boolean }; prev: boolean }> = [];
    const hide = (obj: { visible: boolean }) => {
      hidden.push({ obj, prev: obj.visible });
      obj.visible = false;
    };
    for (const g of this.facade.glassMeshes) hide(g);
    for (const g of this.props.glassMeshes) hide(g);
    hide(this.street.road);
    hide(this.rain.points);
    hide(this.mist.group);

    this.sky.mesh.position.copy(this.cubeCam.position);
    this.cubeCam.update(this.renderer, this.scene);
    const envTex = this.pmrem.fromCubemap(this.cubeRT.texture).texture;
    this.scene.environment = envTex;
    this.facade.setEnvMap(envTex);
    this.props.setEnvMap(envTex);
    this.nature.setEnvMap(envTex);

    for (const h of hidden) h.obj.visible = h.prev;
  }

  private applyEnv(u: ReturnType<Environment['getUniforms']>, time: number): void {
    this.sky.mesh.position.copy(this.camera.position);
    this.sky.apply(u, time);
    this.facade.applyEnvironment(u);
    this.interior.applyEnvironment(u);
    this.street.applyEnvironment(u);
    this.props.applyEnvironment(u);
    this.distant.applyEnvironment(u);
    this.nature.applyEnvironment(u, time, this.lastDt);
    this.lights.applyEnvironment(u);
    this.mist.apply(u);
    this.rain.apply(u, 0, time);
    this.renderer.toneMappingExposure = u.exposure;
    this.scene.background = new Color().setRGB(
      u.skyZenith[0],
      u.skyZenith[1],
      u.skyZenith[2],
    );
  }

  private onResize(): void {
    const w = this.host.clientWidth || window.innerWidth;
    const h = this.host.clientHeight || window.innerHeight;
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, true);
  }


  /** Lock camera, park the distant train, freeze a consistent dusk rain pose. */
  prepareHeroStill(): void {
    this.camera.position.set(5.6, 1.22, 16.8);
    this.controls.target.set(-0.2, 2.62, -0.6);
    this.controls.update();
    this.nature.parkForHeroStill();
    this.elapsed = 3.2;
    const u = this.env.update(0);
    this.applyEnv(u, this.elapsed);
    this.captureEnvironment();
    this.envReady = true;
  }

  setCaptureSize(w: number, h: number): void {
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(w, h, false);
  }

  renderFrame(): void {
    const u = this.env.update(0);
    this.applyEnv(u, this.elapsed);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  toPNGDataURL(): string {
    return this.renderer.domElement.toDataURL('image/png');
  }

  dispose(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
    window.removeEventListener('resize', this.onResize);
    this.controls.dispose();
    this.facade.dispose();
    this.interior.dispose();
    this.street.dispose();
    this.props.dispose();
    this.distant.dispose();
    this.nature.dispose();
    this.lights.dispose();
    this.mist.dispose();
    this.sky.dispose();
    this.rain.dispose();
    this.cubeRT.dispose();
    this.pmrem.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
