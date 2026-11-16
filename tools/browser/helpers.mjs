import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const root = fileURLToPath(new URL('../../', import.meta.url));
export const python = process.env.PYTHON || 'python';
export const results = resolve(root, 'tools/browser/test-results');
process.env.PLAYWRIGHT_BROWSERS_PATH = '0';
const { chromium } = await import('playwright');

export function runPython(args) {
  const command = spawnSync(python, args, {cwd: root, encoding: 'utf8', timeout: 180_000});
  assert.equal(command.status, 0, command.stderr || command.stdout || String(command.error));
  return command.stdout;
}

export async function provision() {
  const temporary = await mkdtemp(join(tmpdir(), 'parallax-browser-'));
  const fixtures = join(temporary, 'fixtures');
  const inventory = JSON.parse(runPython(['tools/browser/make_fixtures.py', fixtures]));
  runPython(['site/build_workbench.py']);
  await mkdir(results, {recursive: true});
  const browser = await chromium.launch({headless: true});
  return {temporary, fixtures, inventory, browser, async close() {
    await browser.close();
    await rm(temporary, {recursive: true, force: true});
  }};
}

export async function companion() {
  const child = spawn(python, ['site/relay_workbench.py'], {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
  let errors = '';
  child.stderr.on('data', chunk => { errors += chunk; });
  const origin = await new Promise((accept, reject) => {
    const timer = setTimeout(() => reject(Error('Companion startup timed out: ' + errors)), 15_000);
    child.once('exit', code => { clearTimeout(timer); reject(Error('Companion exited ' + code + ': ' + errors)); });
    child.stdout.on('data', chunk => {
      const match = String(chunk).match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) {clearTimeout(timer); accept(match[0]);}
    });
  });
  return {origin, async close() {
    if (child.exitCode === null) {
      child.kill('SIGTERM');
      await new Promise(resolveExit => child.once('exit', resolveExit));
    }
    assert.equal(errors, '', 'Companion stderr');
  }};
}

export async function pageFor(t, environment, {origin, viewport = {width: 1280, height: 800}, missing = []} = {}) {
  const violations = [], errors = [];
  const expected = new Set(missing);
  const context = await environment.browser.newContext({viewport, serviceWorkers: 'block'});
  const allowedRoots = [environment.fixtures, join(root, 'build/workbench/dist')];
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    const localFile = url.protocol === 'file:' && allowedRoots.some(directory => fileURLToPath(url).startsWith(directory + sep));
    if (localFile || (origin && url.origin === origin)) return route.continue();
    violations.push(url.href);
    return route.abort('blockedbyclient');
  });
  await context.routeWebSocket('**/*', socket => {violations.push(socket.url()); socket.close();});
  const page = await context.newPage();
  page.setDefaultTimeout(3000);
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => {
    if (message.type() === 'error' && !expected.has(message.location().url)) errors.push(message.text());
  });
  page.on('requestfailed', request => {
    if (!expected.has(request.url())) errors.push(request.url() + ': ' + request.failure()?.errorText);
  });
  page.on('response', response => {
    if (response.status() >= 400 && !expected.has(response.url())) errors.push(response.url() + ': HTTP ' + response.status());
  });
  t.after(async () => {
    await context.close();
    assert.deepEqual(violations, [], 'Unexpected external or WebSocket request');
    assert.deepEqual(errors, [], 'Unexpected browser console/page/resource errors');
  });
  return page;
}

export async function native(environment, name) {
  return JSON.parse(await readFile(join(environment.fixtures, name, 'native.json'), 'utf8'));
}
export function viewerURL(environment, name) {return pathToFileURL(join(environment.fixtures, name, 'index.html')).href;}
export async function importJSON(page, environment, name) {
  await page.locator('[data-tab="evaluation"]').click();
  await page.locator('#json').setInputFiles(join(environment.fixtures, name, 'native.json'));
  await page.waitForFunction(() => document.getElementById('json').value === '');
  await page.locator('#status').filter({hasText: /^Imported native run records\.$/}).waitFor();
  await page.locator('#final-state').waitFor();
  await settleImages(page);
}
export async function finalFrame(page) {
  await page.locator('#round').fill(await page.locator('#round').getAttribute('max'));
  await page.locator('#round').dispatchEvent('input');
}
export async function layout(page, filename) {
  const dimensions = await page.evaluate(() => ({width: innerWidth, scroll: document.documentElement.scrollWidth}));
  assert.ok(dimensions.scroll <= dimensions.width + 1, JSON.stringify(dimensions));
  await page.screenshot({path: join(results, filename + '.png'), fullPage: true});
}

export async function settleImages(page) {
  await page.locator('img:visible').evaluateAll(images => Promise.all(images.map(image => image.decode())));
}
