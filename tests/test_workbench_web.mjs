import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';
import { checkRun } from '../site/web/contracts.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const dist = join(root, 'build/workbench/dist');
const contract = JSON.parse(await readFile(join(dist, 'contract.json'), 'utf8'));
const fixture = JSON.parse(await readFile(join(dist, 'fixture.json'), 'utf8'));
let appInstance = 0;

// Execute the unmodified application module and its real event handlers. This
// harness supplies only browser I/O; it does not establish browser/layout coverage.
async function workbench(t) {
  const nodes = new Map();
  const listeners = new Map();
  const downloads = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      textContent: '', innerHTML: '', click() {}, classList: { toggle() {} },
    });
    return nodes.get(id);
  };
  const io = {
    contract: structuredClone(contract), fixture: structuredClone(fixture),
    mock: structuredClone(fixture),
  };
  const globals = {
    document: {
      getElementById: node,
      querySelector: () => node('footer'),
      querySelectorAll: () => [],
      createElement: () => ({ click() {} }),
      addEventListener: (type, handler) => listeners.set(type, handler),
    },
    location: { hostname: '127.0.0.1' },
    fetch: async url => {
      if (url === 'contract.json') return { json: async () => io.contract };
      if (url === 'fixture.json') return { json: async () => io.fixture };
      if (url === '/api/status') return {
        ok: true, json: async () => ({ commit: contract.commit, token: 'offline-test' }),
      };
      assert.equal(url, '/api/mock');
      if (io.mockError) throw io.mockError;
      return { ok: true, json: async () => io.mock };
    },
    FileReader: class {
      readAsDataURL(file) {
        file.arrayBuffer().then(bytes => {
          this.result = 'data:image/png;base64,' + Buffer.from(bytes).toString('base64');
          this.onload();
        }).catch(error => this.onerror(error));
      }
    },
  };
  for (const [key, value] of Object.entries(globals)) {
    const previous = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { value, writable: true, configurable: true });
    t.after(() => previous
      ? Object.defineProperty(globalThis, key, previous)
      : Reflect.deleteProperty(globalThis, key));
  }
  t.mock.method(URL, 'createObjectURL', blob => {
    downloads.push(blob);
    return 'blob:workbench-test';
  });
  t.mock.method(URL, 'revokeObjectURL', () => {});
  t.mock.method(globalThis, 'setTimeout', callback => { callback(); return 0; });
  await import(pathToFileURL(join(root, 'site/web/app.js')).href + '?test=' + appInstance++);
  const click = id => listeners.get('click')({
    target: { closest: () => ({ id, dataset: {} }) },
  });
  const tab = name => listeners.get('click')({
    target: { closest: () => ({ dataset: { tab: name } }) },
  });
  const select = (id, files) => listeners.get('change')({ target: { id, files } });
  const importJSON = data => select('json', [
    new File([JSON.stringify(data)], 'run.json', { type: 'application/json' }),
  ]);
  const exportJSON = async () => {
    const count = downloads.length;
    await click('export-run');
    assert.equal(downloads.length, count + 1);
    return JSON.parse(await downloads.at(-1).text());
  };
  await tab('evaluation');
  return { node, io, click, tab, select, importJSON, exportJSON };
}

async function nativeFiles(directory) {
  return Promise.all((await readdir(directory)).map(async name =>
    new File([await readFile(join(directory, name))], name)));
}

const malformed = [
  ['calls[0]', data => { data.calls = [null]; }],
  ['calls[0].status', data => { data.calls[0].status = {}; }],
  ['replay[0].communications[0]', data => { data.replay[0].communications = [null]; }],
  ['replay[0].communications[0].text', data => { data.replay[0].communications[0].text = {}; }],
  ['result.win', data => { data.result.win = 'false'; }],
  ['result.loss', data => { data.result.loss = 0; }],
  ['result.completed', data => { data.result.completed = 'true'; }],
  ['result.turns', data => { data.result.turns = '7'; }],
  ['result.scores.SPECTRA', data => { data.result.scores.SPECTRA = '100'; }],
  ['result.budget', data => { data.result.budget = true; }],
  ['result.budget.reported_input_tokens', data => { data.result.budget.reported_input_tokens = '1'; }],
  ['result.budget.unknown_usage_calls', data => { data.result.budget.unknown_usage_calls = null; }],
  ['result.budget.estimated_cost_usd', data => { data.result.budget.estimated_cost_usd = -1; }],
  ['replay[0].state_after', data => { data.replay[0].state_after = []; }],
  ['replay[0].observations', data => { data.replay[0].observations = 'invalid'; }],
  ['replay[0].observations.SPECTRA', data => { data.replay[0].observations.SPECTRA = null; }],
  ['replay[0].observations.SPECTRA.image', data => { data.replay[0].observations.SPECTRA.image = {}; }],
  ['manifest.room', data => { data.manifest.room = {}; }],
  ['phases[0]', data => { data.phases = [null]; }],
  ['final_state', data => { data.final_state = null; }],
  ['images', data => { data.images = []; }],
  ['images entry', data => { data.images = { 'UNTRUSTED_IMAGE_NAME': {} }; }],
];

for (const [field, change] of malformed) {
  test('reject ' + field + ' without replacing the displayed/exported run', async t => {
    const app = await workbench(t);
    await app.importJSON(fixture);
    const previousPanel = app.node('panel').innerHTML;
    const invalid = structuredClone(fixture);
    change(invalid);
    await app.importJSON(invalid);
    assert(app.node('status').textContent.startsWith('Invalid ' + field + ':'),
      app.node('status').textContent);
    assert.equal(app.node('panel').innerHTML, previousPanel);
    assert.deepEqual(await app.exportJSON(), fixture);
    await app.importJSON(fixture);
    assert.equal(app.node('status').textContent, 'Imported native run records.');
  });
}

test('fixture and mock admission use the same validation without losing the selected run', async t => {
  const app = await workbench(t);
  await app.click('fixture');
  const invalid = structuredClone(fixture);
  invalid.calls = [null];
  app.io.fixture = invalid;
  const previousPanel = app.node('panel').innerHTML;
  await app.click('fixture');
  assert.match(app.node('status').textContent, /^Invalid calls\[0\]:/);
  assert.equal(app.node('panel').innerHTML, previousPanel);
  assert.deepEqual(await app.exportJSON(), fixture);
  app.io.mock = invalid;
  await app.tab('offline');
  await app.click('mock');
  assert.match(app.node('status').textContent, /^Invalid calls\[0\]:/);
  assert.doesNotMatch(app.node('panel').innerHTML, /Running…/);
  await app.tab('evaluation');
  assert.deepEqual(await app.exportJSON(), fixture);
});

test('render preparation failure preserves the selected run and panel', async t => {
  const app = await workbench(t);
  await app.importJSON(fixture);
  const previousPanel = app.node('panel').innerHTML;
  const candidate = structuredClone(fixture);
  candidate.manifest.room = 'Replacement must not be committed';
  app.io.contract.goals = null;
  await app.importJSON(candidate);
  assert.equal(app.node('panel').innerHTML, previousPanel);
  assert.deepEqual(await app.exportJSON(), fixture);
});

test('pending mock navigation and fetch failures retain working controls and run state', async t => {
  const app = await workbench(t);
  await app.importJSON(fixture);
  for (const valid of [false, true]) {
    let release;
    app.io.mock = new Promise(resolve => { release = resolve; });
    await app.tab('offline');
    const pending = app.click('mock');
    assert.match(app.node('panel').innerHTML, /<button id="mock"[^>]*disabled/);
    await app.tab('scenario');
    const candidate = structuredClone(fixture);
    if (!valid) candidate.calls = [null];
    release(candidate);
    await pending;
    assert.equal(app.node('title').textContent,
      valid ? 'Recorded-run evaluation' : 'Match configuration');
    if (!valid) assert.match(app.node('status').textContent, /^Invalid calls\[0\]:/);
    await app.tab('offline');
    assert.doesNotMatch(app.node('panel').innerHTML, /<button id="mock"[^>]*disabled/);
  }
  app.io.mockError = Error('Offline test connection failed');
  await app.click('mock');
  assert.equal(app.node('status').textContent, 'Offline test connection failed');
  assert.doesNotMatch(app.node('panel').innerHTML, /Running…/);
  await app.tab('evaluation');
  assert.deepEqual(await app.exportJSON(), fixture);
});

test('malformed JSON and JSONL errors omit content and preserve the selected run', async t => {
  const app = await workbench(t);
  await app.importJSON(fixture);
  const previousPanel = app.node('panel').innerHTML;
  await app.select('json', [new File(['UNTRUSTED_RECORD_CONTENT'], 'run.json')]);
  assert.equal(app.node('status').textContent, 'Invalid run JSON: expected valid JSON.');
  assert.equal(app.node('panel').innerHTML, previousPanel);
  const files = (await nativeFiles(join(root, 'example_run'))).filter(file => file.name !== 'calls.jsonl');
  files.push(new File(['\nUNTRUSTED_RECORD_CONTENT\n'], 'calls.jsonl'));
  await app.select('directory', files);
  assert.equal(app.node('status').textContent, 'Invalid calls.jsonl line 2: expected valid JSON.');
  assert.equal(app.node('panel').innerHTML, previousPanel);
  assert.deepEqual(await app.exportJSON(), fixture);
});

test('native folder export/reimport preserves every PNG byte including the final image', async t => {
  const app = await workbench(t);
  const files = await nativeFiles(join(root, 'example_run'));
  await app.select('directory', files);
  const exported = await app.exportJSON();
  const images = files.filter(file => file.name.endsWith('.png'));
  assert.equal(Object.keys(exported.images).length, images.length);
  assert.equal(images.length, 29);
  for (const file of images) {
    assert.deepEqual(Buffer.from(exported.images[file.name].split(',')[1], 'base64'),
      Buffer.from(await file.arrayBuffer()));
  }
  await app.importJSON(exported);
  assert.deepEqual(await app.exportJSON(), exported);
});

for (const name of ['final_spectator.png', 'turn_00_spectra.png']) {
  test('duplicate image basename ' + name + ' preserves the selected run', async t => {
    const app = await workbench(t);
    await app.importJSON(fixture);
    const previousPanel = app.node('panel').innerHTML;
    const files = await nativeFiles(join(root, 'example_run'));
    files.push(new File(['different image'], name));
    await app.select('directory', files);
    assert.equal(app.node('status').textContent, 'Duplicate image filename: ' + name);
    assert.equal(app.node('panel').innerHTML, previousPanel);
    assert.deepEqual(await app.exportJSON(), fixture);
  });
}

test('missing images and additional provenance remain supported and preserved', async t => {
  const app = await workbench(t);
  const data = structuredClone(fixture);
  delete data.images;
  delete data.replay[0].observations.SPECTRA.image;
  data.manifest.provenance = { version: 1, source: { status: 'unavailable' } };
  await app.importJSON(data);
  assert.equal(app.node('status').textContent, 'Imported native run records.');
  assert.doesNotMatch(app.node('panel').innerHTML, /<img /);
  assert.deepEqual(await app.exportJSON(), data);
  const files = (await nativeFiles(join(root, 'example_run'))).filter(file => !file.name.endsWith('.png'));
  await app.select('directory', files);
  assert.equal(app.node('status').textContent, 'Imported native run records.');
  assert.deepEqual((await app.exportJSON()).images, {});
});

test('non-finite counters and costs are rejected by the contract', () => {
  for (const value of [NaN, Infinity, -Infinity]) {
    const data = structuredClone(fixture);
    data.result.budget.reported_input_tokens = value;
    assert.throws(() => checkRun(data), /Invalid result\.budget\.reported_input_tokens:/);
    data.result.budget.reported_input_tokens = 0;
    data.result.budget.estimated_cost_usd = value;
    assert.throws(() => checkRun(data), /Invalid result\.budget\.estimated_cost_usd:/);
  }
});

test('unknown usage, nullable diagnostics and unfamiliar statuses are retained', async t => {
  const app = await workbench(t);
  const data = structuredClone(fixture);
  data.calls[0].status = 'future_failure_status';
  data.calls[0].usage = null;
  delete data.calls[0].http_status;
  data.result.budget.unknown_usage_calls = 1;
  data.result.budget.estimated_cost_usd = 0.125;
  await app.importJSON(data);
  assert.equal(app.node('status').textContent, 'Imported native run records.');
  assert.match(app.node('panel').innerHTML, /1 calls with unknown usage/);
  assert.match(app.node('panel').innerHTML, /\$0\.125/);
  assert.deepEqual(await app.exportJSON(), data);
});

test('actual one-turn and zero-turn CLI records remain importable', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'parallax-web-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const app = await workbench(t);
  for (const [mode, flags, expectedCode, expectedCalls] of [
    ['smoke', ['--max-turns', '1', '--max-calls', '18'], 0, 9],
    ['partial', ['--max-calls', '10'], 4, 6],
    ['empty', ['--max-calls', '1'], 4, 0],
  ]) {
    const output = join(directory, mode);
    const completed = spawnSync(process.env.PYTHON || 'python', [
      '-m', 'parallax_relay.play', '--mock', '--quiet', '--out', output, ...flags,
    ], { cwd: root, encoding: 'utf8', timeout: 30_000 });
    assert.ifError(completed.error);
    assert.equal(completed.status, expectedCode, completed.stderr);
    assert.equal(completed.stderr, '');
    await app.select('directory', await nativeFiles(output));
    assert.equal(app.node('status').textContent, 'Imported native run records.');
    const exported = await app.exportJSON();
    assert.equal(exported.result.budget.calls_started, expectedCalls);
    assert.equal(exported.result.completed, false);
    assert.equal(exported.result.scores, null);
    assert.match(app.node('panel').innerHTML, /<strong>Incomplete<\/strong>/);
    assert.match(app.node('panel').innerHTML, /<strong>Unscored<\/strong>/);
    assert(Object.hasOwn(exported.images, 'final_spectator.png'));
    if (mode === 'partial') {
      assert.equal(exported.phases.length, 2);
      assert.equal(exported.replay.length, 0);
      assert.match(app.node('panel').innerHTML, /&quot;messages&quot;/);
    }
    app.io.mock = exported;
    await app.tab('offline');
    await app.click('mock');
    assert.equal(app.node('title').textContent, 'Recorded-run evaluation');
    assert.deepEqual(await app.exportJSON(), exported);
    await app.importJSON(exported);
    assert.deepEqual(await app.exportJSON(), exported);
  }
});
