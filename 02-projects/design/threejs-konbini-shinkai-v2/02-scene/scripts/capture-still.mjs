import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outPath = process.env.OUT || resolve(__dirname, '../../01-refs/m1-rain-dusk-v2.png');
const port = process.env.PORT || '5174';
const url = `http://127.0.0.1:${port}/?capture=1`;

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  mkdirSync(dirname(outPath), { recursive: true });

  const preview = spawn('npx', ['vite', 'preview', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: resolve(__dirname, '..'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let ready = false;
  const onData = (buf) => {
    const s = buf.toString();
    process.stdout.write(s);
    if (/Local:|localhost|127\.0\.0\.1/.test(s)) ready = true;
  };
  preview.stdout.on('data', onData);
  preview.stderr.on('data', onData);

  const t0 = Date.now();
  while (!ready && Date.now() - t0 < 20000) await wait(200);
  if (!ready) {
    preview.kill();
    throw new Error('vite preview did not start');
  }

  // Drive system Chrome over CDP
  const { default: puppeteer } = await import('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME || '/usr/bin/google-chrome',
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

  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(60000);
    await page.goto(url, { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => window.__SHOT1_READY === true, { timeout: 30000 });
    await wait(800);
    const dataUrl = await page.evaluate(() => window.__SHOT1_PNG());
    if (!dataUrl || !dataUrl.startsWith('data:image/png')) {
      throw new Error('capture returned no png');
    }
    const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
    writeFileSync(outPath, buf);
    console.log(`wrote ${outPath} (${buf.length} bytes)`);
  } finally {
    await Promise.race([
      browser.close(),
      new Promise((r) => setTimeout(r, 4000)),
    ]);
    try { preview.kill('SIGKILL'); } catch {}
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
