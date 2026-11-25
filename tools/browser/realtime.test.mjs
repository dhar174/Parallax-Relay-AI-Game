import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { after, before, test } from 'node:test';
import { root, python, results } from './helpers.mjs';

process.env.PLAYWRIGHT_BROWSERS_PATH = '0';
const { chromium } = await import('playwright');
const output = join(results, 'realtime');
let browser;
before(async () => { await mkdir(output, {recursive: true}); browser = await chromium.launch({headless: true}); });
after(async () => { if (browser) await browser.close(); });

async function server(t, mode) {
  const child = spawn(python, ['-m', 'parallax_relay.realtime', '--offline', mode, '--spectate'],
    {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
  let stdout = '', stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  t.after(async () => {
    await Promise.all(browser.contexts().map(context => context.close()));
    if (child.exitCode === null && child.signalCode === null) {
      child.kill();
      await new Promise(resolve => child.once('exit', resolve));
    }
    assert.equal(stderr, '', `Server stderr: ${stderr}`);
  });
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error(`Server startup timeout: ${stdout}\n${stderr}`)), 20000);
    child.once('error', error => {clearTimeout(timer); reject(error);});
    child.once('exit', code => {clearTimeout(timer); reject(Error(`Server exited ${code}: ${stdout}\n${stderr}`));});
    child.stdout.on('data', () => {
      const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) {clearTimeout(timer); resolve(match[0]);}
    });
  });
}

async function pageFor(t, origin, viewport, reducedMotion = 'no-preference', device = {}) {
  const context = await browser.newContext({viewport, reducedMotion, serviceWorkers: 'block', ...device});
  const errors = [], external = [];
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === new URL(origin).origin) return route.continue();
    external.push(route.request().url()); return route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  page.on('response', response => {if (response.status() >= 400) errors.push(`${response.url()}: ${response.status()}`);});
  t.after(async () => { await context.close(); assert.deepEqual(external, []); assert.deepEqual(errors, []); });
  await page.goto(origin);
  return page;
}

async function screenshot(page, name) {
  const size = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth}));
  assert.ok(size.document <= size.viewport + 1, `Horizontal overflow: ${JSON.stringify(size)}`);
  const proof = {'manual-0-ready':'discussion-ready', 'reactive-airborne':'jump', 'reactive-complete':'extraction', 'mobile':'mobile', 'manual-0-result':'failed-contact'}[name];
  if (proof && (!process.env.PROOF_FAILURE_ONLY || proof === 'failed-contact')) {
    const directory = join(root, 'runs/visual-proof');
    await mkdir(directory, {recursive:true});
    await page.screenshot({path:join(directory, `${proof}.png`)});
    const metadata = await page.evaluate(() => Object.fromEntries(['run-id','journal-seq','window','tick','phase'].map(id => [id, document.getElementById(id)?.textContent])));
    await writeFile(join(directory, `${proof}.json`), JSON.stringify(metadata, null, 2));
  }
  await page.screenshot({path: join(output, `${name}.png`), fullPage: true});
  const receipt = await page.evaluate(() => Object.fromEntries(['run-id','journal-seq','window','tick','phase'].map(id => [id, document.getElementById(id)?.textContent])));
  await writeFile(join(output, `${name}.json`), JSON.stringify(receipt, null, 2));
}

test('same-tick consequences retain the authoritative pose and show contact cues', {timeout: 45000}, async t => {
  const origin = await server(t, 'manual');
  const page = await pageFor(t, origin, {width: 1280, height: 800});
  const result = await page.evaluate(async () => {
    const {Scene} = await import('/scene.js');
    const scene = new Scene();
    const robot = {x: 768, y: 37, vx: 0, vy: 18, grounded: false, facing: 1, pose: 'ascent'};
    const world = {tick: 2, robots: {SPECTRA: {...robot}, PYRA: {...robot}, FLUX: {...robot}}};
    scene.setWorld(world);
    // A blocked VENT was sampled before the tick's movement, although emitted after state.
    scene.contact({role: 'PYRA', tick: 2, event_kind: 'blocked', x: 768, y: 19, vy: 19, pose: 'takeoff'});
    const afterBlocked = {...scene.world.robots.PYRA};
    const positionText = document.querySelector('#room-positions').textContent;
    scene.contact({role: 'PYRA', tick: 2, event_kind: 'takeoff', x: 768, y: 37, pose: 'takeoff'});
    const takeoff = scene.cues.get('PYRA')?.pose;
    scene.contact({role: 'PYRA', tick: 2, event_kind: 'landing', x: 768, y: 0, pose: 'landing'});
    const landing = scene.cues.get('PYRA')?.pose;
    return {afterBlocked, positionText, takeoff, landing, finalPose: scene.world.robots.PYRA.pose};
  });
  assert.equal(result.afterBlocked.y, 37);
  assert.equal(result.afterBlocked.vy, 18);
  assert.equal(result.afterBlocked.pose, 'ascent');
  assert.match(result.positionText, /PYRA at column 3\.0, height 0\.1 tiles, airborne, ascent/);
  assert.equal(result.takeoff, 'takeoff');
  assert.equal(result.landing, 'landing');
  assert.equal(result.finalPose, 'ascent');
});

test('reactive spectator waits for Start and runs multiple real windows', {timeout: 90000}, async t => {
  const origin = await server(t, 'reactive');
  const page = await pageFor(t, origin, {width: 1280, height: 800});
  await page.locator('#connection').filter({hasText: /connected/i}).waitFor();
  await page.locator('#start').waitFor();
  const initial = await page.locator('#tick').textContent();
  await page.waitForTimeout(500);
  assert.equal(await page.locator('#tick').textContent(), initial, 'No simulation before Start');
  await screenshot(page, 'reactive-before-start');
  const runningID = await page.locator('#run-id').textContent();
  await page.locator('#start').click();
  await page.getByRole('button', {name: 'Fullscreen', exact: true}).click();
  await page.waitForFunction(() => document.fullscreenElement?.id === 'stage-shell');
  await page.getByLabel('Camera', {exact: true}).selectOption('SPECTRA');
  await page.waitForFunction(() => Number(document.querySelector('#window').textContent.match(/\d+/)?.[0] || 0) >= 2, null, {timeout: 60000});
  assert.equal(await page.locator('#run-id').textContent(), runningID);
  await page.getByLabel('Camera', {exact: true}).selectOption('room');
  await page.getByRole('button', {name: 'Exit to dashboard'}).click();
  await page.getByRole('button', {name: 'Fullscreen', exact: true}).waitFor();
  assert.ok(await page.locator('#transcript [data-seq]').count() > 0, 'Public dialogue is visible');
  assert.ok(await page.locator('#consequences [data-seq]').count() > 0, 'Real consequences are visible');
  await screenshot(page, 'reactive-window-2');
  await page.locator('[data-robot][data-authoritative-pose=ascent], [data-robot][data-authoritative-pose=descent]').first().waitFor({state:'attached', timeout:30000});
  await screenshot(page, 'reactive-airborne');
  await page.locator('#sensor-select').selectOption('SPECTRA');
  await page.locator('#sensor-image:visible').waitFor();
  await page.locator('#sensor-image').evaluate(image => image.decode());
  assert.ok(await page.locator('#sensor-image').evaluate(image => image.naturalWidth > 0));
  await page.locator('#result:visible').waitFor({timeout: 30000});
  const journal = await events(page);
  assert.ok(journal.some(event => event.kind === 'consequence' && event.event_kind === 'completed'), 'Actual team checkpoint');
  const lastFlux = journal.findLast(event => event.kind === 'observation' && event.role === 'FLUX');
  const picker = page.locator('#sensor-select');
  const sensorImage = page.locator('#sensor-image:visible');
  await page.setViewportSize({width: 390, height: 800});
  await picker.selectOption('FLUX_RELIEF');
  await sensorImage.waitFor();
  assert.match(await sensorImage.getAttribute('alt'), new RegExp('Circuit Relief illustration for window ' + lastFlux.window));
  assert.match(await page.locator('#sensor-caption').textContent(), new RegExp('Sampled at tick ' + lastFlux.tick));
  const reliefSrc = await sensorImage.getAttribute('src');
  const size = await sensorImage.evaluate(async image => {
    await image.decode();
    return {native: [image.naturalWidth, image.naturalHeight], right: image.getBoundingClientRect().right,
      viewport: document.documentElement.clientWidth};
  });
  assert.deepEqual(size.native, [850, 295]);
  assert.ok(size.right <= size.viewport, 'The sensor image fits the mobile viewport');
  await screenshot(page, 'flux-circuit-relief-mobile');
  await picker.selectOption('FLUX');
  await sensorImage.waitFor();
  assert.match(await sensorImage.getAttribute('alt'), new RegExp('original sensor observation for window ' + lastFlux.window));
  assert.notEqual(await sensorImage.getAttribute('src'), reliefSrc);
  await page.setViewportSize({width: 1280, height: 800});
  await page.locator('#sensor-select').selectOption('SPECTATOR');
  await screenshot(page, 'reactive-complete');
  const beforeReload = await page.locator('#transcript [data-seq]').evaluateAll(nodes => nodes.map(node => node.dataset.seq));
  await page.reload();
  await page.waitForFunction(count => document.querySelectorAll('#transcript [data-seq]').length >= count, beforeReload.length);
  const afterReload = await page.locator('#transcript [data-seq]').evaluateAll(nodes => nodes.map(node => node.dataset.seq));
  assert.deepEqual(afterReload, beforeReload, 'Reload restores each published message once');
  const finishedRun = await page.locator('#run-id').textContent();
  await page.getByRole('button', {name: 'Restart Match'}).click();
  await page.locator('#tick').filter({hasText: /^0$/}).waitFor();
  assert.notEqual(await page.locator('#run-id').textContent(), finishedRun);
  assert.equal(await page.locator('#result').isVisible(), false);
  assert.equal(await page.getByRole('button', {name: 'Start match'}).isEnabled(), true);
});

for (const [name, viewport, reduced] of [
  ['mobile', {width: 390, height: 844}, 'no-preference'],
  ['narrow-reduced', {width: 320, height: 844}, 'reduce'],
]) {
  test(`spectator reflows: ${name}`, {timeout: 45000}, async t => {
    const origin = await server(t, 'reactive');
    const page = await pageFor(t, origin, viewport, reduced);
    await page.locator('#connection').filter({hasText: /connected/i}).waitFor();
    await page.locator('#start').focus();
    assert.equal(await page.locator('#start').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Enter');
    await page.locator('#transcript [data-seq]').first().waitFor();
    await screenshot(page, name);
  });
}

async function events(page) {
  return page.evaluate(async () => {
    const status = await (await fetch('/api/status')).json();
    const all = []; let cursor = 0, batch;
    do {
      const response = await fetch('/api/events?after=' + cursor, {headers: {'X-Relay-Token': status.token}});
      if (!response.ok) throw Error('Event journal HTTP ' + response.status);
      batch = await response.json(); all.push(...batch.events); cursor = batch.cursor;
    } while (batch.has_more);
    return all;
  });
}

async function configure(editor, commands) {
  while (await editor.locator('[data-kind]').count() > 1) await editor.locator('[data-remove]').last().click();
  for (let index = 0; index < commands.length; index++) {
    if (index) await editor.locator('[data-add]').click();
    const command = commands[index];
    await editor.locator('[data-kind]').nth(index).selectOption(command.kind);
    if (command.direction != null) await editor.locator('[data-direction]').nth(index).selectOption(String(command.direction));
    if (command.ticks != null) await editor.locator('[data-ticks]').nth(index).fill(String(command.ticks));
    if (command.jump != null) await editor.locator('[data-jump]').nth(index).fill(String(command.jump));
  }
}

for (const jump of [0, 24]) {
  test(`manual controlled jump offset ${jump}`, {timeout: 90000}, async t => {
    const origin = await server(t, 'manual');
    const page = await pageFor(t, origin, {width: 1280, height: 800});
    await page.locator('#connection').filter({hasText: /^Connected$/}).waitFor();
    await page.locator('#start').click();
    const editor = role => page.locator(`[data-editor="${role}"]`);
    for (const role of ['SPECTRA', 'PYRA', 'FLUX']) await editor(role).locator('[data-submit]:enabled').waitFor();
    await configure(editor('SPECTRA'), [{kind:'RUN', direction:1, ticks:48}]);
    await configure(editor('PYRA'), [{kind:'VENT'}, {kind:'RUN', direction:1, ticks:32}]);
    await configure(editor('FLUX'), [{kind:'REROUTE'}, {kind:'RUN', direction:1, ticks:48}]);
    const tickBefore = await page.locator('#tick').textContent();
    const positionsBefore = await page.locator('[data-robot]').evaluateAll(nodes => nodes.map(n => [n.dataset.robot, n.dataset.x, n.dataset.y]));
    await editor('SPECTRA').locator('[data-submit]').focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    await editor('FLUX').locator('[data-submit]').click();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('#tick').textContent(), tickBefore, 'No early tick before third role');
    assert.deepEqual(await page.locator('[data-robot]').evaluateAll(nodes => nodes.map(n => [n.dataset.robot, n.dataset.x, n.dataset.y])), positionsBefore, 'No early motion');
    await page.evaluate(() => window.scrollTo(0, 0));
    await screenshot(page, `manual-${jump}-ready`);
    await editor('PYRA').locator('[data-submit]').click();
    await page.waitForFunction(() => Number(document.querySelector('#window').textContent.match(/\d+/)?.[0] || 0) >= 2, null, {timeout:30000});
    for (const role of ['SPECTRA', 'PYRA', 'FLUX']) await editor(role).locator('[data-submit]:enabled').waitFor();
    await configure(editor('SPECTRA'), [{kind:'RUN', direction:1, ticks:60, jump}]);
    await configure(editor('PYRA'), [{kind:'WAIT', ticks:1}]);
    await configure(editor('FLUX'), [{kind:'WAIT', ticks:1}]);
    if (jump === 0) {
      await editor('SPECTRA').locator('[data-jump]').fill('60');
      await editor('SPECTRA').locator('[data-submit]').click();
      assert.match(await editor('SPECTRA').locator('[data-feedback]').textContent(), /jump offset/i);
      await editor('SPECTRA').locator('[data-jump]').fill('0');
    }
    for (const role of ['SPECTRA', 'PYRA', 'FLUX']) await editor(role).locator('[data-submit]').click();
    await page.waitForFunction(() => Number(document.querySelector('#tick').textContent.match(/\d+/)?.[0] || 0) >= 240, null, {timeout:30000});
    const journal = await events(page);
    const starts = journal.filter(e => e.kind === 'window_started');
    assert.ok(starts.length >= 2);
    for (const start of starts.slice(0,2)) assert.deepEqual(Object.values(start.starts), [start.tick, start.tick, start.tick]);
    const contacts = journal.filter(e => e.kind === 'consequence' && e.role === 'SPECTRA' && e.window === 2);
    assert.ok(contacts.some(e => e.event_kind === 'takeoff'));
    assert.ok(contacts.some(e => e.event_kind === (jump === 0 ? 'side_contact' : 'landing')));
    if (jump === 24) assert.ok(contacts.some(e => e.event_kind === 'landing' && e.y === 128), JSON.stringify(contacts));
    else assert.ok(contacts.some(e => e.event_kind === 'side_contact'), JSON.stringify(contacts));
    assert.ok(journal.some(e => e.kind === 'consequence' && e.event_kind === 'rerouted'));
    assert.ok(journal.some(e => e.kind === 'dialogue'));
    if (jump === 0) await page.locator('#consequences').scrollIntoViewIfNeeded();
    await screenshot(page, `manual-${jump}-result`);
  });
}

test('restart clears an active manual match and synchronizes another tab', {timeout: 45000}, async t => {
  const origin = await server(t, 'manual');
  const page = await pageFor(t, origin, {width: 1280, height: 800});
  const observer = await page.context().newPage();
  await observer.goto(origin);
  await page.getByRole('button', {name: 'Start match'}).click();
  const spectra = page.locator('[data-editor="SPECTRA"]');
  const pyra = page.locator('[data-editor="PYRA"]');
  const flux = page.locator('[data-editor="FLUX"]');
  await spectra.locator('[data-submit]:enabled').waitFor();
  const oldRun = await page.locator('#run-id').textContent();
  await observer.locator('#run-id').filter({hasText: oldRun}).waitFor();
  await configure(spectra, [{kind:'RUN', direction:1, ticks:42}]);
  await configure(pyra, [{kind:'VENT'}]);
  await configure(flux, [{kind:'REROUTE'}]);
  for (const editor of [spectra, pyra, flux]) await editor.locator('[data-submit]').click();
  await page.locator('#bridge').filter({hasText: 'Powered'}).waitFor();
  await observer.locator('#bridge').filter({hasText: 'Powered'}).waitFor();
  await spectra.locator('[data-submit]:enabled').waitFor();
  await configure(spectra, [{kind:'RUN', direction:1, ticks:57}, {kind:'WAIT', ticks:1}]);
  const restart = page.getByRole('button', {name: 'Restart Match'});
  await restart.focus();
  await page.keyboard.press('Enter');
  for (const tab of [page, observer]) {
    await tab.locator('#phase').filter({hasText: 'Ready to start'}).waitFor();
    await tab.locator('#bridge').filter({hasText: 'Retracted'}).waitFor();
    assert.notEqual(await tab.locator('#run-id').textContent(), oldRun);
    assert.equal(await tab.locator('#tick').textContent(), '0');
    assert.equal(await tab.locator('#transcript [data-seq], #consequences [data-seq]').count(), 0);
    assert.equal(tab.url(), origin);
  }
  assert.equal(await spectra.locator('[data-kind]').count(), 1);
  assert.equal(await spectra.locator('[data-kind]').inputValue(), 'WAIT');
  assert.equal(await spectra.locator('[data-submit]').isEnabled(), false);
  await page.getByRole('button', {name: 'Start match'}).click();
  await spectra.locator('[data-submit]:enabled').waitFor();
});




test('baseline launcher waits for Start and publishes a real fixture resolution', {timeout:60000}, async t => {
  const origin = await server(t, 'baseline');
  const page = await pageFor(t, origin, {width:1280, height:800});
  await page.locator('#connection').filter({hasText: /^Connected$/}).waitFor();
  assert.ok(await page.locator('#circuit-relief-option').evaluate(option => option.hidden && option.disabled));
  const before = await events(page);
  await page.waitForTimeout(500);
  assert.equal((await events(page)).filter(event => event.kind === 'window_started').length, 0);
  assert.ok(before.every(event => event.tick === 0));
  await page.locator('#start').click();
  await page.waitForFunction(() => document.querySelectorAll('#transcript [data-seq]').length > 0, null, {timeout:30000});
  await page.locator('#consequences [data-seq]').first().waitFor({timeout:30000});
  await screenshot(page, 'baseline-live');
});


test('hostile public speech stays inert text', {timeout:45000}, async t => {
  const origin = await server(t, 'reactive');
  const page = await pageFor(t, origin, {width:1280, height:800});
  const hostile = '<img src=x onerror="window.__speechExecuted=1">';
  await page.route('**/api/events?after=*', async route => {
    const response = await route.fetch();
    const body = await response.json();
    for (const event of body.events) if (event.kind === 'dialogue' && event.role === 'SPECTRA') event.text = hostile;
    await route.fulfill({response, json:body});
  });
  await page.locator('#connection').filter({hasText: /^Connected$/}).waitFor();
  await page.locator('#start').click();
  await page.locator('#transcript [data-role="SPECTRA"] p').filter({hasText:hostile}).first().waitFor();
  assert.equal(await page.locator('#transcript img').count(), 0);
  assert.equal(await page.evaluate(() => window.__speechExecuted), undefined);
  await page.unrouteAll({behavior:'wait'});
});

const speechRoles = ['SPECTRA', 'PYRA', 'FLUX'];
const longSpeech = {
  SPECTRA: 'I can see the landing zone past the bridge. Hold your jump until all three of us reach the near edge. '
    + 'I will cross first, check the raised bank, and call out when the path to the shard is clear.\n👩‍🚀 '
    + 'Our meeting point is beside the exit. Wait for my signal before departing.',
  PYRA: 'The motor is still too hot. I am moving to the console to vent it before FLUX reroutes power. '
    + 'Keep clear of the gap while I cool the housing and check the thermal ring. '
    + 'Once it drops, I will confirm we can extend the deck and cross together.',
  FLUX: 'I see the bridge power circuit. I will wait for PYRA to confirm the vent before I reroute it. '
    + 'I can check the spare energy cell on the way to the exit.\nSignal ' + 'X'.repeat(100) + ' ends here.',
};

function speechWorld(positions, y = 0) {
  const robot = {y, vx: 0, vy: 0, grounded: true, facing: 1, pose: 'idle'};
  return {tick: 1, robots: Object.fromEntries(speechRoles.map((role, i) => [role, {...robot, x: positions[i]}]))};
}

async function loadSpeechFixture(page, {world = speechWorld([768, 768, 768]), speech = longSpeech} = {}) {
  const run = await page.evaluate(async () => (await (await fetch('/api/status')).json()).run_id);
  const journal = [
    {kind: 'state', world},
    {kind: 'phase_open', window: 1, phase: 'broadcast'},
    ...speechRoles.map(role => ({kind: 'dialogue', role, text: speech[role], window: 1, phase: 'broadcast'})),
  ];
  await page.route('**/api/events?after=*', route => {
    const after = Number(new URL(route.request().url()).searchParams.get('after'));
    const events = journal.slice(after).map((event, n) => ({...event, seq: after + n + 1, tick: 1}));
    return route.fulfill({json: {events, cursor: journal.length, run_id: run, has_more: false}});
  });
  await page.clock.install();
  await page.reload();
  await page.waitForFunction(() => document.querySelectorAll('#transcript article').length === 3);
  return journal;
}

async function bubbleScroll(page) {
  return page.locator('.bubble.speaking .bubble-message').evaluateAll(nodes => nodes.map(node => ({
    top: node.scrollTop, end: node.scrollHeight - node.clientHeight, font: parseFloat(getComputedStyle(node).fontSize),
  })));
}

async function assertBubblesFit(page) {
  const {viewport, boxes, overflow} = await page.evaluate(() => {
    const dock = document.querySelector('#stage-viewport[data-speech-docked] #bubbles');
    const viewport = (dock || document.querySelector('#stage-scroll')).getBoundingClientRect().toJSON();
    if (!dock) viewport.bottom = viewport.top + document.querySelector('#stage').clientHeight;
    const boxes = [...document.querySelectorAll('.bubble:not([hidden])')].map(node => node.getBoundingClientRect().toJSON());
    return {viewport, boxes, overflow: document.documentElement.scrollWidth - innerWidth};
  });
  assert.ok(overflow <= 1, 'Speech does not widen the page');
  assert.ok(boxes.length >= 3);
  for (const [i, box] of boxes.entries()) {
    assert.ok(box.left >= viewport.left && box.right <= viewport.right &&
      box.top >= viewport.top && box.bottom <= viewport.bottom, `Bubble ${i} is inside the stage`);
    assert.ok(boxes.slice(0, i).every(other => box.right <= other.left || box.left >= other.right ||
      box.bottom <= other.top || box.top >= other.bottom), `Bubble ${i} does not overlap another`);
  }
}

for (const native of [true, false]) {
  test(`${native ? 'native' : 'fallback'} presentation controls fit at doubled text size`, {timeout:45000}, async t => {
    const origin = await server(t, 'manual');
    const page = await pageFor(t, origin, {width: 320, height: 568}, 'reduce');
    await loadSpeechFixture(page, {world: presentationFixture()});
    await page.evaluate(native => {
      document.documentElement.style.fontSize = '32px';
      if (!native) document.querySelector('#stage-shell').requestFullscreen = undefined;
    }, native);
    const toggle = page.locator('#stage-fullscreen');
    assert.ok(await toggle.evaluate(button => button.getBoundingClientRect().right <=
      button.closest('.scene-panel').getBoundingClientRect().right), 'Dashboard launcher fits in its panel');
    await toggle.click();
    await page.locator(`#stage-shell[data-presentation="${native ? 'native' : 'game-only'}"]`).waitFor();
    await assertPresentationControlsFit(page);
    await page.getByRole('button', {name: 'Exit to dashboard'}).click();
    await page.getByRole('button', {name: 'Fullscreen', exact: true}).waitFor();
  });
}

async function assertPresentationControlsFit(page) {
  const clipped = await page.locator('#stage-controls :is(button, select)').evaluateAll(controls => controls
    .filter(control => {
      const rect = control.getBoundingClientRect();
      return rect.left < -1 || rect.right > document.documentElement.clientWidth + 1 ||
        rect.top < -1 || rect.bottom > document.documentElement.clientHeight + 1;
    }).map(control => control.id));
  assert.deepEqual(clipped, [], 'All stage controls stay reachable');
}

for (const scenario of ['robot', 'short', 'movement']) {
  test(`crowded follow speech stays usable during ${scenario}`, {timeout:45000}, async t => {
    const origin = await server(t, 'manual');
    const width = scenario === 'movement' ? 780 : 568;
    const height = scenario === 'short' ? 200 : 320;
    const x = scenario === 'movement' ? 320 : 1536;
    const page = await pageFor(t, origin, {width, height}, 'reduce');
    const world = {...speechWorld([x, 768, 1024]), bridge_powered: true};
    const journal = await loadSpeechFixture(page, {world});
    await page.locator('#stage-shell').evaluate(el => {el.requestFullscreen = undefined;});
    await page.locator('#stage-fullscreen').click();
    await page.getByLabel('Camera', {exact: true}).selectOption('SPECTRA');
    if (scenario !== 'movement') await page.getByLabel('Text size', {exact: true}).selectOption('largest');
    await waitForFollowScale(page, 'SPECTRA');
    if (scenario === 'movement') {
      const rows = () => page.locator('.bubble.speaking').evaluateAll(nodes => nodes.map(node => node.offsetTop));
      const before = await rows();
      await publishPose(page, journal, {...world, robots: {...world.robots,
        SPECTRA: {...world.robots.SPECTRA, x: x + 16}}}, 2);
      assert.deepEqual(await rows(), before, 'A single physics tick keeps each speaker in the same row');
    }
    await assertBubblesFit(page);
    assert.ok(await page.evaluate(() => {
      const robot = document.querySelector('[data-robot="SPECTRA"] .robot-art').getBoundingClientRect();
      return [...document.querySelectorAll('.bubble.speaking')].every(node => {
        const bubble = node.getBoundingClientRect();
        return bubble.right <= robot.left || bubble.left >= robot.right ||
          bubble.bottom <= robot.top || bubble.top >= robot.bottom;
      });
    }), 'All speech stays clear of the followed robot');
    await page.getByRole('button', {name: 'Read speech'}).click();
    assert.equal(await page.getByRole('region', {name: 'Complete message'}).textContent(), longSpeech.FLUX);
  });
}

test('long released speech is visible and intact on a narrow stage', {timeout:45000}, async t => {
  const origin = await server(t, 'manual');
  const page = await pageFor(t, origin, {width: 320, height: 780});
  const journal = await loadSpeechFixture(page);
  for (const role of speechRoles) {
    const text = page.locator(`[data-bubble="${role}"] .bubble-message`);
    assert.ok(await text.isVisible(), `${role}'s bubble should show speech at 320px`);
    assert.equal(await text.textContent(), longSpeech[role]);
  }
  await assertBubblesFit(page);
  assert.ok(await page.evaluate(() => {
    const artTop = document.querySelector('.robot-art').getBoundingClientRect().top;
    return [...document.querySelectorAll('.bubble.speaking')].every(node => node.getBoundingClientRect().bottom <= artTop);
  }), 'Crowded bubbles leave the grounded robots visible');
  await page.screenshot({path: join(output, 'speech-320.png')});
  const initial = await bubbleScroll(page);
  assert.ok(initial.every(row => row.top === 0 && row.end > 0 && row.font >= 16));
  await page.clock.fastForward(6000);
  const scrolled = await bubbleScroll(page);
  assert.ok(scrolled.every(row => row.top > 0 && row.top < row.end), 'All three bubbles scroll concurrently');

  const feed = page.getByLabel('Choose view');
  await feed.selectOption('PYRA');
  assert.equal(await page.locator('#stage').isVisible(), false);
  await page.clock.fastForward(3000);
  await feed.selectOption('SPECTATOR');
  const returned = await bubbleScroll(page);
  assert.ok(returned.every((row, i) => row.top > scrolled[i].top), 'Returning to the stage restores current reading progress');

  await page.getByRole('button', {name: 'Pause scrolling'}).click();
  const paused = await bubbleScroll(page);
  journal.push({kind: 'state', world: speechWorld([0, 1536, 3072])});
  await page.clock.fastForward(10_000);
  await page.waitForFunction(() => document.querySelector('[data-robot="FLUX"]').dataset.x === '3072');
  assert.deepEqual(await bubbleScroll(page), paused, 'Pose and journal updates do not reset speech or advance paused text');

  await page.setViewportSize({width: 390, height: 844});
  const textSize = page.getByLabel('Text size', {exact: true});
  await textSize.selectOption('large');
  assert.ok((await bubbleScroll(page)).every(row => row.font === 18));
  await textSize.selectOption('largest');
  assert.ok((await bubbleScroll(page)).every(row => row.font === 20));
  await assertBubblesFit(page);
  await page.getByRole('button', {name: 'Enlarge room'}).click();
  await page.locator('#stage-scroll').evaluate(el => { el.scrollLeft = 400; });
  await page.waitForFunction(() => document.querySelector('[data-bubble="SPECTRA"]').dataset.offscreen === 'left');
  assert.equal(await page.locator('[data-bubble="FLUX"]').getAttribute('data-offscreen'), 'right');
  await assertBubblesFit(page);

  await page.getByRole('button', {name: 'Resume scrolling'}).click();
  await page.clock.fastForward(60_000);
  assert.ok((await bubbleScroll(page)).every(row => Math.abs(row.top - row.end) <= 1), 'Every bubble reaches its final line');

  const read = page.getByRole('button', {name: 'Read speech'});
  await read.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', {name: 'Public speech'});
  assert.ok(await dialog.isVisible());
  const complete = dialog.getByRole('region', {name: 'Complete message'});
  assert.equal(await complete.textContent(), longSpeech.FLUX);
  assert.equal(await complete.evaluate(el => getComputedStyle(el).fontSize), '20px');
  await page.screenshot({path: join(output, 'speech-reader-390.png')});
  const nextText = '<img src=x onerror="window.__speechExecuted=1">';
  journal.push({kind: 'phase_open', window: 2, phase: 'broadcast'});
  await page.clock.fastForward(400);
  await page.waitForFunction(() => document.querySelector('#window').textContent === '2');
  assert.equal(await complete.textContent(), longSpeech.FLUX, 'Opening a phase does not replace a message being read');
  assert.equal(await page.locator('[data-bubble="FLUX"] .bubble-message').textContent(), longSpeech.FLUX);
  journal.push({kind: 'dialogue', role: 'SPECTRA', text: nextText, window: 2, phase: 'broadcast'});
  await page.waitForFunction(() => document.querySelectorAll('#transcript article').length === 4);
  assert.equal(await complete.textContent(), longSpeech.FLUX, 'New dialogue does not replace the open message');
  await dialog.getByRole('button', {name: 'Previous'}).click();
  assert.equal(await complete.textContent(), longSpeech.PYRA);
  await dialog.getByRole('button', {name: 'Next'}).click();
  await dialog.getByRole('button', {name: 'Next'}).click();
  assert.equal(await complete.textContent(), nextText);
  assert.equal(await dialog.locator('img').count(), 0);
  await page.keyboard.press('Escape');
  assert.equal(await dialog.isVisible(), false);
  assert.ok(await read.evaluate(el => el === document.activeElement));

  await page.setViewportSize({width: 1280, height: 800});
  await page.getByRole('button', {name: 'Room overview'}).click();
  await textSize.selectOption('normal');
  assert.equal(await page.locator('[data-bubble="SPECTRA"] .bubble-message').textContent(), nextText);
  assert.equal(await page.locator('#bubbles img').count(), 0);
  assert.equal(await page.evaluate(() => window.__speechExecuted), undefined);
  assert.deepEqual(await bubbleScroll(page), [{top: 0, end: 0, font: 16}], 'Entire short message fits at desktop size');
  await assertBubblesFit(page);
});

test('reduced motion stops automatic bubble scrolling until the viewer resumes', {timeout:45000}, async t => {
  const origin = await server(t, 'manual');
  const page = await pageFor(t, origin, {width: 390, height: 844}, 'reduce');
  await loadSpeechFixture(page);
  assert.ok(await page.getByRole('button', {name: 'Resume scrolling'}).isVisible());
  await page.clock.fastForward(6000);
  assert.ok((await bubbleScroll(page)).every(row => row.top === 0 && row.end > 0));
  await page.getByRole('button', {name: 'Resume scrolling'}).click();
  await page.clock.fastForward(6000);
  assert.ok((await bubbleScroll(page)).every(row => row.top > 0));
});

for (const compact of [true, false]) {
  const layout = compact ? 'compact' : 'regular';
  test(`${layout} speech bubbles keep their rows when speakers cross`, {timeout:45000}, async t => {
    const origin = await server(t, 'manual');
    const page = await pageFor(t, origin, {width: 320, height: 780});
    const speech = compact ? longSpeech : {...longSpeech, PYRA: 'The vent is ready.'};
    // Put the regular case near the top edge so nearby placement uses different rows.
    const elevation = compact ? 0 : 1280;
    const journal = await loadSpeechFixture(page, {world: speechWorld([756, 768, 780], elevation), speech});
    assert.equal(await page.locator('#bubbles[data-compact]').count(), Number(compact));
    await page.clock.fastForward(6000);
    const scrolling = (await bubbleScroll(page)).filter(row => row.end > 0);
    assert.equal(scrolling.length, compact ? 3 : 2);
    assert.ok(scrolling.every(row => row.top > 0 && row.top < row.end));

    const rowPositions = () => page.locator('.bubble.speaking').evaluateAll(nodes =>
      Object.fromEntries(nodes.map(node => [node.dataset.bubble, node.offsetTop])));
    const before = await rowPositions();
    // Reverse the robots' horizontal order with roughly two pixels of movement.
    journal.push({kind: 'state', world: speechWorld([780, 768, 756], elevation)});
    await page.waitForFunction(() => document.querySelector('[data-robot="SPECTRA"]').dataset.x === '780');
    assert.deepEqual(await rowPositions(), before, 'Every speaker stays in the same row');
    await assertBubblesFit(page);
  });
}

function presentationFixture() {
  const world = speechWorld([128, 1024, 3000]);
  world.robots.FLUX.y = 128;
  return world;
}

async function framing(page, role) {
  return page.locator(`[data-robot="${role}"] .robot-art`).evaluate(art => {
    const stage = document.querySelector('#stage').getBoundingClientRect();
    const actor = art.getBoundingClientRect();
    return {width: actor.width, x: actor.left - stage.left, y: actor.top - stage.top,
      right: stage.right - actor.right, bottom: stage.bottom - actor.bottom};
  });
}

function assertInFrame(frame) {
  assert.ok(frame.width > 0 && [frame.x, frame.y, frame.right, frame.bottom].every(value => value >= -1),
    `Robot is fully framed: ${JSON.stringify(frame)}`);
}

async function waitForFollowScale(page, role) {
  // ResizeObserver applies the new projection after the viewport's CSS size changes.
  await page.waitForFunction(role => {
    const stage = document.querySelector('#stage');
    const width = stage.clientWidth, height = stage.clientHeight;
    const tilesAcross = width < height ? 5 : 6.5;
    const expectedWidth = Math.min(width / tilesAcross, height / 3.5) * 8 / 9;
    const art = document.querySelector(`[data-robot="${role}"] .robot-art`);
    return Math.abs(art.getBoundingClientRect().width - expectedWidth) < 1;
  }, role);
}

async function publishPose(page, journal, world, tick) {
  journal.push({kind: 'state', world: {...world, tick}});
  await page.waitForFunction(tick => document.querySelector('#stage').dataset.tick === String(tick), tick);
}

test('native fullscreen shares camera and dialogue without resetting the match', {timeout:45000}, async t => {
  const origin = await server(t, 'manual');
  const page = await pageFor(t, origin, {width: 1280, height: 800});
  const journal = await loadSpeechFixture(page, {world: presentationFixture()});
  const camera = page.getByLabel('Camera', {exact: true});
  const enter = page.getByRole('button', {name: 'Fullscreen', exact: true});
  const exit = page.getByRole('button', {name: 'Exit to dashboard'});
  assert.equal(await camera.inputValue(), 'room');
  await page.getByRole('button', {name: 'Enlarge room'}).click();
  const pan = await page.locator('#stage-scroll').evaluate(node => {node.scrollLeft = 190; return node.scrollLeft;});
  assert.ok(pan > 0);
  const runID = await page.locator('#run-id').textContent();
  await enter.focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.fullscreenElement?.id === 'stage-shell');
  assert.equal(await page.locator('#stage-shell').getAttribute('data-presentation'), 'native');
  assert.equal(await camera.inputValue(), 'room');
  assert.ok(await page.locator('#start').evaluate(node => Boolean(node.closest('[inert]'))));
  const room = await framing(page, 'SPECTRA');
  for (const role of speechRoles) assertInFrame(await framing(page, role));
  await assertBubblesFit(page);
  await page.screenshot({path: join(output, 'fullscreen-whole-room.png')});

  for (const role of speechRoles) {
    await camera.selectOption(role);
    await waitForFollowScale(page, role);
    const followed = await framing(page, role);
    assert.ok(followed.width > room.width * 1.4);
    assertInFrame(followed);
  }
  await page.screenshot({path: join(output, 'fullscreen-follow.png')});
  const jumping = presentationFixture();
  Object.assign(jumping.robots.FLUX, {x: 2880, y: 320, grounded: false, pose: 'ascent'});
  await publishPose(page, journal, jumping, 2);
  assertInFrame(await framing(page, 'FLUX'));
  const respawn = presentationFixture();
  Object.assign(respawn.robots.FLUX, {x: 128, y: 0, pose: 'idle'});
  await publishPose(page, journal, respawn, 3);
  assertInFrame(await framing(page, 'FLUX'));

  const read = page.getByRole('button', {name: 'Read speech'});
  await read.click();
  const dialog = page.getByRole('dialog', {name: 'Public speech'});
  assert.ok(await dialog.isVisible());
  assert.equal(await dialog.getByRole('region', {name: 'Complete message'}).textContent(), longSpeech.FLUX);
  journal.push({kind: 'dialogue', role: 'PYRA', text: 'Ready for the next jump.', window: 2, phase: 'broadcast'});
  await page.waitForFunction(() => document.querySelectorAll('#transcript article').length === 4);
  assert.equal(await dialog.getByRole('region', {name: 'Complete message'}).textContent(), longSpeech.FLUX);
  assert.ok(await dialog.evaluate(node => document.fullscreenElement?.contains(node)));
  assert.equal(await page.locator('#run-id').textContent(), runID);
  await dialog.getByRole('button', {name: 'Close'}).click();
  await camera.selectOption('room');
  await exit.click();
  await page.waitForFunction(() => !document.fullscreenElement && !document.querySelector('#stage-shell').dataset.presentation);
  assert.equal(await page.locator('#stage-scroll').evaluate(node => node.scrollLeft), pan);
  assert.ok(await enter.evaluate(node => node === document.activeElement));

  await camera.selectOption('PYRA');
  await enter.click();
  await page.waitForFunction(() => document.fullscreenElement?.id === 'stage-shell');
  assert.equal(await camera.inputValue(), 'PYRA');
  await page.evaluate(() => document.exitFullscreen());
  await enter.waitFor();
  assert.equal(await camera.inputValue(), 'PYRA');
  assert.ok(await enter.evaluate(node => node === document.activeElement));
  assert.equal(await page.locator('#start').evaluate(node => Boolean(node.closest('[inert]'))), false);
});

for (const unavailable of [true, false]) {
  const reason = unavailable ? 'unavailable' : 'denied';
  test(`game-only fallback when native fullscreen is ${reason}`, {timeout:45000}, async t => {
    const origin = await server(t, 'manual');
    const width = unavailable ? 320 : 390;
    const page = await pageFor(t, origin, {width, height: 780}, 'reduce', {hasTouch: true, isMobile: true});
    const journal = await loadSpeechFixture(page, {world: presentationFixture()});
    await page.evaluate(unavailable => {
      if (unavailable) document.querySelector('#stage-shell').requestFullscreen = undefined;
      else document.querySelector('#stage-shell').requestFullscreen = () => Promise.reject(new Error('Denied by test'));
    }, unavailable);
    const enter = page.getByRole('button', {name: 'Fullscreen', exact: true});
    await page.evaluate(() => window.scrollTo(0, 160));
    await enter.scrollIntoViewIfNeeded();
    const scrollY = await page.evaluate(() => window.scrollY);
    assert.ok(scrollY > 0, 'Exercise restoration of a scrolled dashboard');
    await enter.tap();
    await page.getByText('Game-only view', {exact: true}).waitFor();
    assert.equal(await page.evaluate(() => document.fullscreenElement), null);
    assert.ok(await page.locator('#sensor-select').evaluate(node => Boolean(node.closest('[inert]'))));
    const camera = page.getByLabel('Camera', {exact: true});
    const whole = await framing(page, 'SPECTRA');
    await camera.selectOption('SPECTRA');
    const followed = await framing(page, 'SPECTRA');
    assert.ok(followed.width > whole.width * 2, 'Portrait follow zoom admits the surrounding terrain');
    assertInFrame(followed);
    const landing = presentationFixture();
    Object.assign(landing.robots.SPECTRA, {x: 2656, y: 128, pose: 'landing'});
    await publishPose(page, journal, landing, 2);
    assertInFrame(await framing(page, 'SPECTRA'));
    await assertBubblesFit(page);
    assert.ok(await page.evaluate(() => {
      const actor = document.querySelector('[data-robot="SPECTRA"] .robot-art').getBoundingClientRect();
      return [...document.querySelectorAll('.bubble.speaking')].every(node => {
        const bubble = node.getBoundingClientRect();
        return bubble.right <= actor.left || bubble.left >= actor.right ||
          bubble.bottom <= actor.top || bubble.top >= actor.bottom;
      });
    }), 'The followed robot stays visible below the bubbles');
    if (unavailable) await page.screenshot({path: join(output, 'game-only-320.png')});

    await page.getByRole('button', {name: 'Read speech'}).tap();
    const dialog = page.getByRole('dialog', {name: 'Public speech'});
    assert.ok(await dialog.isVisible());
    await page.keyboard.press('Escape');
    await dialog.waitFor({state: 'hidden'});
    assert.equal(await page.locator('#stage-shell').getAttribute('data-presentation'), 'game-only');
    await page.setViewportSize({width: 780, height: 320});
    await page.waitForFunction(() => document.querySelector('#stage-shell').clientWidth === 780);
    await waitForFollowScale(page, 'SPECTRA');
    assertInFrame(await framing(page, 'SPECTRA'));
    await assertBubblesFit(page);
    await page.setViewportSize({width, height: 780});
    await page.keyboard.press('Escape');
    await enter.waitFor();
    assert.equal(await page.evaluate(() => window.scrollY), scrollY);
    assert.ok(await enter.evaluate(node => node === document.activeElement));
    assert.equal(await camera.inputValue(), 'SPECTRA');
  });
}
