import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { readFile, writeFile, cp } from 'node:fs/promises';
import { provision, pageFor, runPython, root } from './helpers.mjs';

let environment;
const exported = name => join(environment.fixtures, 'spectator-' + name);
const exportURL = name => pathToFileURL(join(exported(name), 'index.html')).href;

before(async () => {
  environment = await provision();
  // Keep the attack in the actual native log, not just the old viewer fixture.
  const attackRun = join(environment.fixtures, 'malicious');
  const attack = JSON.parse(await readFile(join(attackRun, 'native.json'), 'utf8'));
  for (const key of ['replay', 'phases', 'calls']) {
    await writeFile(join(attackRun, key + '.jsonl'), attack[key].map(row => JSON.stringify(row)).join('\n') + '\n');
  }
  const withheld = join(environment.fixtures, 'withheld');
  await cp(join(environment.fixtures, 'win'), withheld, {recursive: true});
  const manifestPath = join(withheld, 'manifest.json');
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  manifest.provenance ??= {};
  manifest.provenance.execution ??= {};
  manifest.provenance.execution.value ??= {};
  manifest.provenance.execution.value.conditions = {arm: 'withheld'};
  await writeFile(manifestPath, JSON.stringify(manifest));
  for (const name of ['win', 'later-partial', 'legacy-v2', 'missing-images', 'malicious', 'withheld']) {
    runPython(['tools/spectator/export_replay.py', join(environment.fixtures, name), '--out', exported(name)]);
  }
});
after(async () => {if (environment) await environment.close();});

test('default spectator uses the illustrated board and each role feed shows its original PNG', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  assert.equal(await page.locator('[data-feed="SPECTATOR"] .select').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#feedBoard').isVisible(), true);
  assert.equal(await page.locator('#feedImage').isVisible(), false);
  const native = JSON.parse(await readFile(join(environment.fixtures, 'win', 'native.json'), 'utf8'));
  for (const feed of ['SPECTRA', 'PYRA', 'FLUX']) {
    await page.locator(`[data-feed="${feed}"] .select`).click();
    assert.equal(await page.locator(`[data-feed="${feed}"] .select`).getAttribute('aria-pressed'), 'true');
    assert.match(await page.locator('#feedTitle').textContent(), new RegExp(feed));
    assert.equal(await page.locator('#feedBoard').isVisible(), false);
    await page.locator('#feedImage').waitFor({state: 'visible'});
    assert.ok(await page.locator('#feedImage').evaluate(img => img.complete && img.naturalWidth > 0));
    assert.equal(await page.locator('#feedImage').getAttribute('src'), native.images['turn_00_' + feed.toLowerCase() + '.png']);
  }
});

test('expanded feed keeps round in sync and Escape restores focus', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  const expand = page.getByRole('button', {name: 'Expand PYRA feed'});
  await expand.click();
  assert.equal(await page.locator('#dialog').evaluate(el => el.open), true);
  assert.match(await page.locator('#dialogTitle').textContent(), /PYRA/);
  await page.locator('#dialogNext').click();
  assert.equal(await page.locator('#dialogRound').inputValue(), '1');
  assert.equal(await page.locator('#round').inputValue(), '1');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#dialog').evaluate(el => el.open), false);
  assert.equal(await expand.evaluate(el => el === document.activeElement), true);
  assert.match(await page.locator('#feedTitle').textContent(), /PYRA/);
  assert.match(await page.locator('#roundLabel').textContent(), /Round 2/);
});

test('navigation reaches the recorded final checkpoint', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  assert.equal(await page.locator('#prev').isDisabled(), true);
  await page.locator('#next').click();
  assert.equal(await page.locator('#round').inputValue(), '1');
  const slider = page.locator('#round');
  await slider.fill(await slider.getAttribute('max'));
  await slider.dispatchEvent('input');
  assert.match(await page.locator('#roundLabel').textContent(), /final/i);
  assert.equal(await page.locator('#next').isDisabled(), true);
  const native = JSON.parse(await readFile(join(environment.fixtures, 'win', 'native.json'), 'utf8'));
  assert.deepEqual(JSON.parse(await page.locator('#finalState').textContent()), native.final_state);
  assert.equal(await page.locator('#feedBoard').isVisible(), true);
  assert.equal(await page.locator('#feedImage').isVisible(), false);
});

test('partial and historical v2 runs remain navigable', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('later-partial'));
  const slider = page.locator('#round');
  const max = Number(await slider.getAttribute('max'));
  assert.ok(max >= 2);
  await slider.fill(String(max - 1));
  await slider.dispatchEvent('input');
  assert.match(await page.locator('#roundLabel').textContent(), /unfinished|unknown/i);
  const partial = JSON.parse(await readFile(join(environment.fixtures, 'later-partial', 'native.json'), 'utf8'));
  await assertBoard(page, partial.final_state);
  await slider.fill(String(max));
  await slider.dispatchEvent('input');
  assert.match(await page.locator('#roundLabel').textContent(), /final/i);
  await page.goto(exportURL('legacy-v2'));
  assert.equal(await page.locator('#feedBoard').isVisible(), false);
  await page.locator('#feedImage').waitFor({state: 'visible'});
  assert.ok(await page.locator('#feedImage').evaluate(img => img.naturalWidth > 0));
  assert.ok(Number(await page.locator('#round').getAttribute('max')) > 0);
  await page.locator('#next').click();
  assert.match(await page.locator('#roundLabel').textContent(), /Round 2/);
});

test('missing images give an explicit fallback', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('missing-images'));
  await page.locator('[data-feed="PYRA"] .select').click();
  assert.equal(await page.locator('#feedMissing').isVisible(), true);
  assert.equal(await page.locator('#feedImage').isVisible(), false);
  await page.getByRole('button', {name: 'Expand FLUX feed'}).click();
  assert.equal(await page.locator('#dialogMissing').isVisible(), true);
});

for (const width of [320, 390]) {
  test(`viewport ${width} has no horizontal overflow`, async t => {
    const page = await pageFor(t, environment, {viewport: {width, height: 844}});
    await page.goto(exportURL('win'));
    const dimensions = await page.evaluate(() => ({viewport: innerWidth, content: document.documentElement.scrollWidth}));
    assert.ok(dimensions.content <= dimensions.viewport + 1, JSON.stringify(dimensions));
    await page.getByRole('button', {name: 'Expand SPECTATOR feed'}).click();
    assert.equal(await page.locator('#dialogBoard').isVisible(), true);
    const dialog = await page.locator('#dialog').evaluate(el => ({width: el.clientWidth, scroll: el.scrollWidth}));
    assert.ok(dialog.scroll <= dialog.width + 1, JSON.stringify(dialog));
  });
}

test('untrusted model text is shown as text without execution or network requests', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('malicious'));
  assert.match(await page.locator('#chat').textContent(), /invalid\.example\/probe/);
  assert.equal(await page.evaluate(() => window.modelExecuted), undefined);
  assert.equal(await page.locator('#chat img, #chat script').count(), 0);
});

test('final checkpoint displays spectator and restores the selected role on return', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  await page.locator('[data-feed="PYRA"] .select').click();
  const slider = page.locator('#round');
  const max = Number(await slider.getAttribute('max'));
  await slider.fill(String(max));
  await slider.dispatchEvent('input');
  assert.match(await page.locator('#feedTitle').textContent(), /SPECTATOR/);
  assert.match(await page.locator('#resultSummary').textContent(), /Outcome:.*Scores:/);
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) {
    assert.equal(await page.locator(`[data-feed="${role}"] .select`).isDisabled(), true);
    assert.equal(await page.locator(`[data-feed="${role}"] .expand`).isDisabled(), true);
  }
  await slider.fill(String(max - 1));
  await slider.dispatchEvent('input');
  assert.match(await page.locator('#feedTitle').textContent(), /PYRA/);
  assert.equal(await page.locator('[data-feed="PYRA"] .select').getAttribute('aria-pressed'), 'true');
});

test('role feed limits private details and diagnostics to that role', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) {
    await page.locator(`[data-feed="${role}"] .select`).click();
    const privateText = await page.locator('#private').textContent();
    assert.match(privateText, new RegExp(role + ' (goal|notes|HUD)'));
    for (const other of ['SPECTRA', 'PYRA', 'FLUX'].filter(r => r !== role)) {
      assert.doesNotMatch(privateText, new RegExp(other + ' (goal|notes|HUD)'));
    }
    const diagnostics = await page.locator('#diagnostics .entry').allTextContents();
    assert.ok(diagnostics.length > 0);
    assert.ok(diagnostics.every(text => text.startsWith(role + ' /')));
    assert.equal(await page.locator('#phases .entry').count(), 0);
  }
});

test('withheld communication condition is disclosed', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('withheld'));
  assert.match(await page.locator('#condition').textContent(), /withheld.*withheld from other players/i);
});

test('spectator-only records disappear on role feeds and after returning from final', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  await page.locator('details > summary').click();
  assert.equal(await page.locator('#spectatorRecords').isVisible(), true);
  assert.notEqual(await page.locator('#finalState').textContent(), '');
  await page.locator('[data-feed="PYRA"] .select').click();
  assert.equal(await page.locator('#spectatorRecords').isVisible(), false);
  assert.equal(await page.locator('#finalState').textContent(), '');
  assert.equal(await page.locator('#ungrouped').textContent(), '');
  const slider = page.locator('#round');
  const max = Number(await slider.getAttribute('max'));
  await slider.fill(String(max));
  await slider.dispatchEvent('input');
  assert.equal(await page.locator('#spectatorRecords').isVisible(), true);
  assert.notEqual(await page.locator('#finalState').textContent(), '');
  await slider.fill(String(max - 1));
  await slider.dispatchEvent('input');
  assert.equal(await page.locator('#spectatorRecords').isVisible(), false);
  assert.equal(await page.locator('#finalState').textContent(), '');
  assert.equal(await page.locator('#ungrouped').textContent(), '');
});


async function seek(page, index) {
  await page.locator('#round').fill(String(index));
  await page.locator('#round').dispatchEvent('input');
}

async function assertBoard(page, state) {
  const board = page.locator('#feedBoard');
  assert.equal(await board.isVisible(), true);
  const stage = board.locator('.board-stage');
  const accessible = await stage.getAttribute('aria-label');
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) {
    assert.match(accessible, new RegExp(role + ' at tile ' + state.robots[role].x + '(?:,|\\.)'));
  }
  const status = await board.locator('.board-status').textContent();
  for (const value of ['Energy: ' + state.energy, 'Coolant: ' + state.coolant,
    'Motor heat: ' + state.motor_heats.bridge_0,
    'Bridge: ' + (state.powered_bridges.includes('bridge_0') ? 'extended' : 'retracted'),
    'Exit: ' + (state.exit_unlocked ? 'unlocked' : 'locked')]) assert.ok(status.includes(value), status);
  assert.equal(await stage.locator('.tile').count(), state.powered_bridges.includes('bridge_0') ? 13 : 10);
  assert.equal(await stage.getByAltText('Memory shard').count(), state.shard_collected ? 0 : 1);
  assert.equal(await stage.getByAltText('Energy cell').count(), state.collected_cells.includes(10) ? 0 : 1);
  const exit = stage.getByAltText(state.exit_unlocked ? 'Unlocked exit' : 'Locked exit');
  const artwork = await readFile(join(root, 'tools/spectator/artwork/light-review', state.exit_unlocked ? 'exit-open.png' : 'exit-closed.png'));
  assert.equal(await exit.getAttribute('src'), 'data:image/png;base64,' + artwork.toString('base64'));
  assert.equal(await stage.locator('.exit-label').textContent(), state.exit_unlocked ? 'Exit unlocked' : 'Exit locked');
}

test('illustrated board tracks each recorded checkpoint and loads real artwork', async t => {
  const page = await pageFor(t, environment);
  const native = JSON.parse(await readFile(join(environment.fixtures, 'win', 'native.json'), 'utf8'));
  await page.goto(exportURL('win'));
  const states = [native.manifest.provenance.inputs.room.value.initial_state,
    ...native.replay.slice(0, -1).map(row => row.state_after), native.final_state];
  assert.ok(states.some(state => state.powered_bridges.includes('bridge_0')));
  assert.ok(states.some(state => state.shard_collected));
  assert.ok(states.some(state => state.collected_cells.includes(10)));
  assert.equal(native.final_state.exit_unlocked, true);
  for (let i = 0; i < states.length; i++) {
    await seek(page, i);
    await assertBoard(page, states[i]);
    assert.ok(await page.locator('#feedBoard .board-stage').evaluate(async stage => {
      const background = getComputedStyle(stage).backgroundImage;
      if (!background.startsWith('url("data:image/png;base64,')) return false;
      const image = new Image();
      image.src = background.slice(5, -2);
      await image.decode();
      return image.naturalWidth > 0;
    }));
    assert.ok(await page.locator('#feedBoard img').evaluateAll(images => Promise.all(images.map(image => image.decode().then(() => image.naturalWidth > 0))).then(results => results.every(Boolean))));
    const positions = Object.values(states[i].robots).map(robot => robot.x);
    if (new Set(positions).size < 3) {
      const lefts = await page.locator('#feedBoard .robot').evaluateAll(images => images.map(image => image.style.left));
      assert.equal(new Set(lefts).size, 3, 'robots sharing a tile remain separately positioned');
    }
  }
});

test('expanded spectator board stays synchronized and Escape restores focus', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  const expand = page.getByRole('button', {name: 'Expand SPECTATOR feed'});
  await expand.click();
  assert.equal(await page.locator('#dialogBoard').isVisible(), true);
  await page.locator('#dialogNext').click();
  assert.equal(await page.locator('#dialogRound').inputValue(), await page.locator('#round').inputValue());
  assert.equal(await page.locator('#dialogBoard .board-stage').getAttribute('aria-label'),
    await page.locator('#feedBoard .board-stage').getAttribute('aria-label'));
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#dialog').evaluate(el => el.open), false);
  assert.equal(await expand.evaluate(el => el === document.activeElement), true);
});

test('stale role image callbacks cannot replace the spectator board', async t => {
  const page = await pageFor(t, environment);
  await page.goto(exportURL('win'));
  const result = await page.evaluate(() => {
    document.querySelector('[data-feed="PYRA"] .select').click();
    const img = document.querySelector('#feedImage');
    const previous = img.onload;
    document.querySelector('[data-feed="SPECTATOR"] .select').click();
    if (previous) previous();
    return {hadCallback: typeof previous === 'function', imageHidden: img.hidden,
      boardHidden: document.querySelector('#feedBoard').hidden, missingHidden: document.querySelector('#feedMissing').hidden};
  });
  assert.deepEqual(result, {hadCallback: true, imageHidden: true, boardHidden: false, missingHidden: true});
});
