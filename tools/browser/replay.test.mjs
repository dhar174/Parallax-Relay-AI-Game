import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { provision, companion, pageFor, native, viewerURL, importJSON, finalFrame, layout, results, root, settleImages } from './helpers.mjs';

let environment;
before(async () => {environment = await provision();});
after(async () => {if (environment) await environment.close();});

const cases = [
  ['win', 'victory', 7, 63, 21], ['turn-limit', 'turn_limit', 1, 9, 3],
  ['later-partial', 'call_budget', 1, 15, 5], ['zero-turn-partial', 'call_budget', 0, 6, 2],
  ['zero-call', 'call_budget', 0, 0, 0], ['local-error', 'local_error', 0, 3, 1],
  ['cancelled', 'cancelled', 0, 3, 0],
];

for (const [name, stop, turns, calls, phases] of cases) {
  test('file viewer retains native final checkpoint and all diagnostics: ' + name, async t => {
    const data = await native(environment, name);
    assert.deepEqual(environment.inventory[name], {stop_reason: stop, turns, calls, phases});
    assert.equal(data.result.budget.calls_started, calls);
    const page = await pageFor(t, environment);
    await page.goto(viewerURL(environment, name));
    assert.match(await page.title(), /Parallax Relay/);
    assert.equal(await page.locator('#calls').textContent(), String(calls));
    assert.equal(await page.locator('#turnCount').textContent(), String(turns));
    const resolved = new Set(data.replay.map(record => record.turn - 1));
    const partial = new Set([...data.calls, ...data.phases].map(record => record.turn).filter(turn => !resolved.has(turn)));
    assert.equal(Number(await page.locator('#round').getAttribute('max')), turns + partial.size, 'Only resolved, evidenced partial and final frames exist');
    await finalFrame(page);
    assert.match(await page.locator('#roundLabel').textContent(), /final/i);
    assert.deepEqual(JSON.parse(await page.locator('#finalState').textContent()), data.final_state);
    assert.match(await page.locator('#SPECTATOR').getAttribute('src'), /final_spectator\.png$/);
    assert.ok(await page.locator('#SPECTATOR').evaluate(async image => {await image.decode(); return image.naturalWidth > 0;}));
    // Every recorded call/phase is available when its actual frame is selected.
    let shownCalls = 0, shownPhases = 0;
    const callText = [], phaseText = [];
    for (let index = 0; index < Number(await page.locator('#round').getAttribute('max')); index++) {
      await page.locator('#round').fill(String(index));
      await page.locator('#round').dispatchEvent('input');
      await settleImages(page);
      callText.push(...await page.locator('#diagnostics .entry').allTextContents());
      phaseText.push(...await page.locator('#phases .entry').allTextContents());
      shownCalls += await page.locator('#diagnostics .entry').count();
      shownPhases += await page.locator('#phases .entry').count();
      if (index >= turns) {
        assert.equal(await page.locator('#actions .entry').count(), 0, 'Partial phase has no invented actions');
        assert.equal(await page.locator('#events .entry').count(), 0, 'Partial phase has no invented engine events');
      }
    }
    assert.equal(shownCalls, calls, 'Each native attempt must remain visible exactly once');
    assert.equal(shownPhases, phases, 'Each completed native phase must remain visible exactly once');
    for (const call of data.calls) assert.ok(callText.some(text => text.includes(JSON.stringify(call))), 'Complete native call diagnostic');
    for (const phase of data.phases) assert.ok(phaseText.some(text => text.includes(JSON.stringify(phase))), 'Complete native phase diagnostic');
    if (turns === 0 && calls === 0) {
      assert.equal(await page.locator('#actions .entry').count(), 0);
      assert.equal(await page.locator('#events .entry').count(), 0);
    }
  });
}

test('file viewer keyboard controls have names, boundaries, focus and live updates', async t => {
  const page = await pageFor(t, environment);
  await page.goto(viewerURL(environment, 'win'));
  assert.equal(await page.getByRole('button', {name: 'Previous round'}).isDisabled(), true);
  await page.keyboard.press('Tab');
  assert.equal(await page.getByRole('slider', {name: 'Recorded round'}).evaluate(el => el === document.activeElement), true);
  const before = await page.locator('#roundLabel').textContent();
  await page.keyboard.press('ArrowRight');
  await settleImages(page);
  assert.notEqual(await page.locator('#roundLabel').textContent(), before);
  await page.keyboard.press('Tab');
  assert.equal(await page.getByRole('button', {name: 'Next round'}).evaluate(el => el === document.activeElement), true);
  await page.keyboard.press('Enter');
  await settleImages(page);
  assert.equal(await page.locator('#round').inputValue(), '2');
  await page.getByRole('button', {name: 'Previous round'}).click();
  await settleImages(page);
  assert.equal(await page.locator('#round').inputValue(), '1');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('#round').evaluate(el => el === document.activeElement), true);
  assert.notEqual(await page.locator('#round').evaluate(el => getComputedStyle(el).outlineStyle), 'none');
  assert.ok(['polite', 'assertive'].includes(await page.locator('#roundLabel').getAttribute('aria-live')));
  await page.keyboard.press('End');
  await settleImages(page);
  assert.equal(await page.getByRole('button', {name: 'Next round'}).isDisabled(), true);
  await page.keyboard.press('Home');
  await settleImages(page);
  assert.equal(await page.getByRole('button', {name: 'Previous round'}).isDisabled(), true);
  assert.equal(await page.locator('#round').inputValue(), '0');
});

for (const viewport of [{width: 1280, height: 800}, {width: 390, height: 844}]) {
  test('file viewer fits viewport and exposes readable text: ' + viewport.width, async t => {
    const page = await pageFor(t, environment, {viewport});
    await page.goto(viewerURL(environment, 'later-partial'));
    await finalFrame(page);
    await page.getByText('Final world snapshot (spectator only)', {exact: true}).click();
    await layout(page, 'standalone-' + viewport.width);
    const label = page.locator('#roundLabel');
    assert.ok(await label.isVisible());
    const contrast = await label.evaluate(el => {
      const values = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(c => {c /= 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;});
      const luminance = c => {const [r,g,b] = values(c); return .2126*r+.7152*g+.0722*b;};
      const foreground = luminance(getComputedStyle(el).color), background = luminance(getComputedStyle(document.documentElement).backgroundColor);
      return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
    });
    assert.ok(contrast >= 4.5, 'Round-label contrast ' + contrast);
    await writeFile(join(results, 'contrast-' + viewport.width + '.json'), JSON.stringify({viewport, roundLabelContrast: contrast}, null, 2));
  });
}

test('model strings remain inert in standalone and workbench partial data', async t => {
  const server = await companion();
  t.after(() => server.close());
  const page = await pageFor(t, environment, {origin: server.origin});
  await page.goto(viewerURL(environment, 'malicious'));
  assert.match(await page.locator('#room').textContent(), /onerror=/);
  await page.locator('#round').fill('1');
  await page.locator('#round').dispatchEvent('input');
  await settleImages(page);
  assert.match(await page.locator('#chat').textContent(), /window.modelExecuted/);
  assert.equal(await page.evaluate(() => window.modelExecuted), undefined);
  assert.equal(await page.locator('img[src^="https:"]').count(), 0);
  await page.goto(server.origin);
  await importJSON(page, environment, 'malicious-import');
  assert.match(await page.locator('#partial-rounds').textContent(), /window.modelExecuted/);
  assert.equal(await page.evaluate(() => window.modelExecuted), undefined);
  assert.equal(await page.locator('img[src^="https:"]').count(), 0);
});

test('missing images are explicit without losing final state or diagnostics', async t => {
  const base = pathToFileURL(join(environment.fixtures, 'missing-images') + '/').href;
  const missing = ['turn_00_spectra.png', 'turn_00_pyra.png', 'turn_00_flux.png', 'turn_00_spectator.png', 'final_spectator.png'].map(name => base + name);
  const page = await pageFor(t, environment, {missing});
  await page.goto(viewerURL(environment, 'missing-images'));
  await finalFrame(page);
  assert.deepEqual(JSON.parse(await page.locator('#finalState').textContent()), (await native(environment, 'missing-images')).final_state);
  await page.locator('#SPECTATORUnavailable').waitFor({state: 'visible'});
  assert.equal(await page.locator('#SPECTATOR').isVisible(), false);
  assert.match(await page.locator('#SPECTATORUnavailable').textContent(), /unavailable|missing/i);
});

test('built workbench imports actual legacy v2 and new v3 directories and JSON', async t => {
  const server = await companion();
  t.after(() => server.close());
  const page = await pageFor(t, environment, {origin: server.origin});
  await page.goto(server.origin);
  assert.match(await page.title(), /Parallax Relay/);
  await page.locator('[data-tab="evaluation"]').click();
  await page.getByRole('button', {name: 'Import run folder', exact: true}).focus();
  const chooser = page.waitForEvent('filechooser');
  await page.keyboard.press('Enter');
  await (await chooser).setFiles(join(root, 'example_run'));
  await page.locator('#final-state').waitFor();
  assert.deepEqual(JSON.parse(await page.locator('#final-state pre').textContent()), (await native(environment, 'legacy-v2')).final_state);
  assert.ok(await page.locator('#final-spectator').evaluate(async image => {await image.decode(); return image.naturalWidth > 0;}));
  await page.locator('#directory').setInputFiles(join(environment.fixtures, 'later-partial'));
  await page.waitForFunction(() => document.getElementById('directory').value === '');
  assert.deepEqual(JSON.parse(await page.locator('#final-state pre').textContent()), (await native(environment, 'later-partial')).final_state);
  for (const [name] of cases) {
    await importJSON(page, environment, name);
    const data = await native(environment, name);
    assert.deepEqual(JSON.parse(await page.locator('#final-state pre').textContent()), data.final_state);
    const allPhases = page.locator('details').filter({has: page.getByText('All phase records, including unfinished rounds', {exact: true})}).locator('pre');
    assert.deepEqual(JSON.parse(await allPhases.textContent()), data.phases);
    if (name === 'later-partial' || name === 'zero-turn-partial') {
      assert.match(await page.locator('#partial-rounds').textContent(), /broadcast|negotiate/);
    }
  }
  await importJSON(page, environment, 'missing-images');
  assert.match(await page.locator('#final-spectator').textContent(), /unavailable/i);
  assert.deepEqual(JSON.parse(await page.locator('#final-state pre').textContent()), (await native(environment, 'missing-images')).final_state);
  await importJSON(page, environment, 'later-partial');
  await page.getByText('Final world snapshot', {exact: true}).click();
  for (const viewport of [{width: 1280, height: 800}, {width: 390, height: 844}]) {
    await page.setViewportSize(viewport);
    await layout(page, 'workbench-' + viewport.width);
  }
});

test('actual loopback companion executes one-turn mock through built workbench', async t => {
  const server = await companion();
  t.after(() => server.close());
  const page = await pageFor(t, environment, {origin: server.origin});
  await page.goto(server.origin);
  await page.locator('[data-match="max_turns"]').fill('1');
  await page.locator('[data-tab="offline"]').click();
  const response = page.waitForResponse(response => response.url() === server.origin + '/api/mock', {timeout: 60_000});
  await page.getByRole('button', {name: 'Run offline through Python', exact: true}).click();
  const data = await (await response).json();
  assert.equal(data.result.stop_reason, 'turn_limit');
  assert.equal(data.result.turns, 1);
  assert.equal(data.calls.length, 9);
  await page.locator('#final-state').waitFor();
  assert.deepEqual(JSON.parse(await page.locator('#final-state pre').textContent()), data.final_state);
  assert.ok(await page.locator('#final-spectator').evaluate(async image => {await image.decode(); return image.naturalWidth > 0;}));
});


test('current file viewer reads actual legacy v2 final artifacts', async t => {
  const data = await native(environment, 'legacy-v2');
  assert.equal(data.manifest.schema_version, 2);
  const page = await pageFor(t, environment);
  await page.goto(viewerURL(environment, 'legacy-v2'));
  await finalFrame(page);
  assert.deepEqual(JSON.parse(await page.locator('#finalState').textContent()), data.final_state);
  assert.ok(await page.locator('#SPECTATOR').evaluate(async image => {await image.decode(); return image.naturalWidth > 0;}));
});
