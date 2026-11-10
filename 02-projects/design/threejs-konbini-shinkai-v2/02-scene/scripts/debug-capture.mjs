import puppeteer from 'puppeteer-core';
const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: 'new',
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--ignore-gpu-blocklist',
    '--enable-webgl',
    '--use-gl=angle',
    '--use-angle=swiftshader-webgl',
    '--window-size=1920,1080',
  ],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const logs = [];
page.on('console', (m) => logs.push(`CONSOLE ${m.type()}: ${m.text()}`));
page.on('pageerror', (e) => logs.push(`PAGEERROR: ${e.message}\n${e.stack}`));
page.on('requestfailed', (r) => logs.push(`REQFAIL: ${r.url()} ${r.failure()?.errorText}`));
try {
  await page.goto('http://127.0.0.1:5175/?capture=1', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await new Promise((r) => setTimeout(r, 4000));
  const info = await page.evaluate(() => ({
    ready: window.__SHOT1_READY,
    hasPng: typeof window.__SHOT1_PNG,
    title: document.title,
    canvas: !!document.querySelector('canvas'),
    canvasSize: (() => {
      const c = document.querySelector('canvas');
      return c ? [c.width, c.height] : null;
    })(),
    body: document.body.innerText.slice(0, 300),
    webgl: (() => {
      try {
        const c = document.createElement('canvas');
        return !!(c.getContext('webgl2') || c.getContext('webgl'));
      } catch (e) {
        return String(e);
      }
    })(),
  }));
  console.log('INFO', JSON.stringify(info, null, 2));
  console.log('LOGS\n' + logs.join('\n'));
} finally {
  await browser.close();
}
