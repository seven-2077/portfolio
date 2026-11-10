import { World } from './scene/World';
import { Environment } from './env/Environment';

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) {
  throw new Error('#app not found');
}

const env = new Environment();
const params = new URLSearchParams(location.search);
const capture = params.has('capture');

if (capture) {
  app.style.width = '1920px';
  app.style.height = '1080px';
  document.body.style.overflow = 'hidden';
  const hint = document.getElementById('hint');
  if (hint) hint.style.display = 'none';
}

const world = new World(app, env);

if (capture) {
  world.setCaptureSize(1920, 1080);
  world.prepareHeroStill();
  // Warm up transmission, reflector, and instance materials
  for (let i = 0; i < 8; i++) world.renderFrame();
  window.__SHOT1_READY = true;
  window.__SHOT1_PNG = () => {
    world.prepareHeroStill();
    for (let i = 0; i < 4; i++) world.renderFrame();
    return world.toPNGDataURL();
  };
} else {
  world.start();
}

window.addEventListener('beforeunload', () => {
  world.dispose();
});

declare global {
  interface Window {
    __SHOT1_READY?: boolean;
    __SHOT1_PNG?: () => string;
  }
}
