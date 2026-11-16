import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';
import {runInNewContext} from 'node:vm';
import { checkRun, validate, toml } from '../site/web/contracts.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const dist = join(root, 'build/workbench/dist');
const contract = JSON.parse(await readFile(join(dist, 'contract.json'), 'utf8'));
const fixture = JSON.parse(await readFile(join(dist, 'fixture.json'), 'utf8'));
const smokeProfile = JSON.parse(await readFile(join(root, 'configs/live_smoke.json'), 'utf8'));
smokeProfile.config.match.condition = null;
smokeProfile.config.match.room_id = 'split_span';
let appInstance = 0;

test('development room selector exports strings, preserves selection for smoke and excludes held-out execution',async t=>{
 const app=await workbench(t);await app.tab('scenario');
 assert.match(app.node('panel').innerHTML,/<select data-match="room_id">/);
 assert.doesNotMatch(app.node('panel').innerHTML,/<option value="ret_01"/);
 app.input({dataset:{match:'room_id'},value:'dev_01'});
 await app.click('smoke');assert.match(await app.exportConfig(),/room_id = "dev_01"/);
 const bad=structuredClone(contract.defaults);bad.match.room_id='ret_01';
 assert.throws(()=>validate(bad,contract),/room|held-out/);
});

test('offline copy identifies Split Span fixture separately from the selected room',async t=>{
 const app=await workbench(t);await app.tab('scenario');
 app.input({dataset:{match:'room_id'},value:'dev_02'});await app.tab('offline');
 assert.match(app.node('panel').innerHTML,/original Split Span fixture/);
 assert.match(app.node('panel').innerHTML,/selected development room and may fail/);
});

test('workbench retains a historical v1 communication label',async t=>{
 const app=await workbench(t);const data=structuredClone(fixture);
 data.manifest.provenance={schema_version:1,execution:{value:{conditions:{communication:'reduced'}}}};
 await app.importJSON(data);assert.match(app.node('panel').innerHTML,/Condition: reduced/);
});

test('editing rounds after a named condition remains exportable and smoke repairs empty rounds', async t => {
  const app=await workbench(t);
  await app.tab('scenario');
  for(const condition of ['disabled','reduced']){
    app.input({dataset:{match:'condition'},value:condition});
    assert.equal(app.node('match-communication_rounds').value,condition==='disabled'?'0':'1');
    const panel=app.node('panel').innerHTML;
    app.input({dataset:{match:'communication_rounds'},value:'2',valueAsNumber:2});
    assert.equal(app.node('match-condition').value,'');
    assert.match(await app.exportConfig(),/communication_rounds = 2/);
    assert.doesNotMatch(await app.exportConfig(),/condition =/);
    app.input({dataset:{match:'condition'},value:condition});
    assert.equal(app.node('panel').innerHTML,panel,'condition changes must not rebuild the focused selector');
    app.input({dataset:{match:'communication_rounds'},value:'',valueAsNumber:NaN});
    await app.click('smoke');
    const expected=condition==='disabled'?0:1;
    const output=await app.exportConfig();
    assert.match(output,new RegExp('communication_rounds = '+expected));
    assert.match(output,new RegExp('condition = "'+condition+'"'));
    assert.match(output,new RegExp('max_calls = '+(3*(expected+1)*contract.defaults.match.max_attempts)));
  }
});

test('unselecting a named arm preserves empty rounds without writing NaN',async t=>{
 const app=await workbench(t);await app.tab('scenario');
 app.input({dataset:{match:'condition'},value:'disabled'});
 app.input({dataset:{match:'communication_rounds'},value:'',valueAsNumber:NaN});
 app.input({dataset:{match:'condition'},value:''});
 assert.equal(app.node('match-communication_rounds').value,'');
 assert.doesNotMatch(app.node('match-communication_rounds').value,/NaN/);
});

test('replay header names the recorded room safely and keeps the historical fallback',async()=>{
 const template=await readFile(join(root,'parallax_relay/replay_template.html'),'utf8');
 for(const [manifest,label] of [[{schema_version:3,room:'dev_02'},'dev_02'],[{schema_version:2},'The Split Span'],[{schema_version:3},'Room unspecified'],[{schema_version:3,room:'<img src=x onerror=alert(1)>'},'<img src=x onerror=alert(1)>']]){
  const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'0',textContent:'',replaceChildren(){},closest(){return this;},addEventListener(){}});return nodes.get(id);};
  const data={manifest,records:[],calls:[],result:{stop_reason:'turn_limit',turns:0,budget:{calls_started:0},energy:6}};
  const script=template.match(/<script>([\s\S]*?)<\/script>/)[1].replace('__REPLAY_DATA__',JSON.stringify(data));
  runInNewContext(script,{document:{getElementById:node,createElement:()=>({}),createTextNode:()=>({})}});
  assert.equal(node('room').textContent,label+' · recorded match');
 }
});

test('actual replay script labels policies and historical v1 conditions truthfully',async()=>{
  const template=await readFile(join(root,'parallax_relay/replay_template.html'),'utf8');
  for(const policy of ['wait','uniform','scripted']){
    const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'0',textContent:'',replaceChildren(){},closest(){return this;},addEventListener(){}});return nodes.get(id);};
    const manifest={mode:'mock',provenance:{execution:{value:{policy:{name:policy},conditions:{communication:'reduced'}}}}};
    const data={manifest,records:[],calls:[],result:{stop_reason:'turn_limit',turns:0,budget:{calls_started:0},energy:6}};
    const script=template.match(/<script>([\s\S]*?)<\/script>/)[1].replace('__REPLAY_DATA__',JSON.stringify(data));
    runInNewContext(script,{document:{getElementById:node,createElement:()=>({}),createTextNode:()=>({})}});
    assert.match(node('mode').textContent,new RegExp(policy==='scripted'?'SCRIPTED FIXTURE':policy.toUpperCase()+' POLICY'));
    assert.match(node('condition').textContent,/Condition: reduced/);
  }
});

test('additive settlement split is validated and retained on export', async t => {
  const app = await workbench(t);
  const data = structuredClone(fixture);
  data.result.budget.known_usage_estimated_usd = 0;
  data.result.budget.retained_estimate_usd = null;
  await app.importJSON(data);
  assert.deepEqual(await app.exportJSON(), data);
  assert.match(app.node('panel').innerHTML, /Known-usage priced estimate/);
  assert.match(app.node('panel').innerHTML, /Known-usage priced estimate: \$0/);
  assert.match(app.node('panel').innerHTML, /Retained unknown-usage estimate: Unavailable/);
  for(const key of ['known_usage_estimated_usd','retained_estimate_usd','reserved_estimated_usd']){
    for(const value of [NaN,Infinity,-Infinity]){
      const bad=structuredClone(fixture);bad.result.budget[key]=value;
      assert.throws(()=>checkRun(bad),new RegExp(key));
    }
  }
  data.result.budget.retained_estimate_usd = -1;
  assert.throws(() => checkRun(data), /retained_estimate_usd/);
});

test('all evaluation conditions export Python-valid settings and reset approval', async t => {
  const app = await workbench(t);
  await app.click('live-smoke');
  for (const condition of ['full', 'reduced', 'disabled', 'withheld', 'no_images']) {
    await app.tab('live'); await app.click('approve');
    await app.tab('scenario');
    app.input({ dataset: { match: 'condition' }, value: condition });
    const text = await app.exportConfig();
    const parsed = spawnSync(process.env.PYTHON || 'python', ['-c',
      'import sys,tomllib; from parallax_relay.config import GameConfig; c=GameConfig.model_validate(tomllib.loads(sys.stdin.read())); print(c.match.condition)'],
      { cwd: root, input: text, encoding: 'utf8' });
    assert.equal(parsed.status, 0, parsed.stderr);
    assert.equal(parsed.stdout.trim(), condition);
    await app.tab('live');
    assert.doesNotMatch(app.node('panel').innerHTML, /approved-download/);
  }
});

test('named live preset exports Python-valid settings and exact independent role models', async t => {
  const app = await workbench(t);
  await app.tab('scenario');
  await app.click('live-smoke');
  const text = await app.exportConfig();
  assert.ok(text.includes('max_output_tokens = 4096'), 'Named preset was not applied');
  const parsed = spawnSync(process.env.PYTHON || 'python', ['-c',
    'import sys,json,tomllib; from parallax_relay.config import GameConfig; print(json.dumps(GameConfig.model_validate(tomllib.loads(sys.stdin.read())).model_dump()))'],
    { cwd: root, input: text, encoding: 'utf8' });
  assert.equal(parsed.status, 0, parsed.stderr);
  assert.deepEqual(JSON.parse(parsed.stdout), smokeProfile.config);
  await app.tab('live');
  assert.match(app.node('panel').innerHTML, /gpt-6-luna/);
  assert.match(app.node('panel').innerHTML, /gemini-3\.5-flash-lite/);
  assert.match(app.node('panel').innerHTML, /scripts\/live_smoke\.py --check/);
  assert.match(app.node('panel').innerHTML, /href="https:\/\/developers\.openai\.com\/api\/docs\/pricing\.md"/);
  assert.match(app.node('panel').innerHTML, /free-tier eligibility\/quota unverified/);
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) {
    const source = smokeProfile.sources[role];
    const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
    for (const url of [source.model_url, source.pricing_url]) {
      assert.ok(app.node('panel').innerHTML.includes(`href="${escape(url)}"`), `${role} source link missing`);
    }
    assert.ok(app.node('panel').innerHTML.includes(escape(source.notes)), `${role} notes missing`);
  }
  await app.click('approve');
  assert.match(app.node('panel').innerHTML, /scripts\/live_smoke\.py --live/);
  app.input({ dataset: { match: 'max_calls' }, value: '17', valueAsNumber: 17 });
  await app.tab('live');
  assert.doesNotMatch(app.node('panel').innerHTML, /approved-download/);
  assert.doesNotMatch(app.node('panel').innerHTML, /scripts\/live_smoke\.py --live/);
});

test('semantically matching preset survives reordered configuration properties', async t => {
  const modified = structuredClone(contract);
  modified.defaults = Object.fromEntries(Object.entries(smokeProfile.config).reverse());
  modified.defaults.players = Object.fromEntries(Object.entries(modified.defaults.players).reverse().map(([role, player]) =>
    [role, Object.fromEntries(Object.entries(player).reverse())]));
  const app = await workbench(t, { contract: modified });
  await app.tab('live');
  assert.match(app.node('panel').innerHTML, /Named live-smoke roster/);
});

test('old and additive usage-origin records survive import and export', async t => {
  const app = await workbench(t);
  for (const annotated of [false, true]) {
    const data = structuredClone(fixture);
    if (annotated) data.calls[0].usage.source_usage = {
      'usage.cache_read_input_tokens': { state: 'null', value: null },
    };
    await app.importJSON(data);
    assert.deepEqual(await app.exportJSON(), data);
  }
});

// Execute the unmodified application module and its real event handlers. This
// harness supplies only browser I/O; it does not establish browser/layout coverage.
async function workbench(t, overrides = {}) {
  const nodes = new Map();
  const listeners = new Map();
  const downloads = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      textContent: '', innerHTML: '', value: '', click() {},
      classList: {
        values: new Set(),
        toggle(name, enabled) { if (enabled) this.values.add(name); else this.values.delete(name); },
        contains(name) { return this.values.has(name); },
      },
      setAttribute(name, value) { this[name] = value; },
      removeAttribute(name) { delete this[name]; },
    });
    return nodes.get(id);
  };
  const io = {
    contract: structuredClone(contract), fixture: structuredClone(fixture),
    mock: structuredClone(fixture), ...overrides,
  };
  const globals = {
    document: {
      getElementById: node,
      querySelector: selector => selector==='.sidefoot'?node('footer'):
        node('match-'+selector.match(/^\[data-match="([a-z_]+)"\]$/)[1]),
      querySelectorAll: () => ['scenario', 'offline', 'live', 'evaluation'].map(tab => {
        const button = node('nav-' + tab);
        button.dataset = { tab };
        return button;
      }),
      createElement: () => ({ click() {} }),
      addEventListener: (type, handler) => listeners.set(type, handler),
    },
    location: { hostname: '127.0.0.1' },
    fetch: async url => {
      if (url === 'contract.json') return { ok: !io.contractError, json: async () => io.contract };
      if (url === 'fixture.json') return { ok: !io.fixtureError, json: async () => io.fixture };
      if (url === '/api/status') return {
        ok: true, json: async () => ({ commit: contract.commit, token: 'offline-test' }),
      };
      assert.equal(url, '/api/mock');
      if (io.mockError) throw io.mockError;
      return { ok: true, json: async () => io.mock };
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
  const select = async (id, files) => {
    const target = { id, files, value: 'selected-path' };
    await listeners.get('change')({ target });
    return target;
  };
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
  const input = target => listeners.get('input')({ target });
  const exportConfig = async () => {
    const count = downloads.length;
    await click('export-config');
    return downloads.length === count ? null : downloads.at(-1).text();
  };
  return { node, io, click, tab, select, importJSON, exportJSON, input, exportConfig, downloads };
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
    assert.equal(app.node('title').textContent, 'Match configuration');
    assert.equal(app.node('status').textContent, '');
    await app.tab('offline');
    assert.doesNotMatch(app.node('panel').innerHTML, /<button id="mock"[^>]*disabled/);
  }
  app.io.mockError = Error('Offline test connection failed');
  await app.click('mock');
  assert.equal(app.node('status').textContent, 'Offline execution failed. Check the local companion.');
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
  assert.match(app.node('panel').innerHTML, /<img /);
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

test('badInput cannot silently remove a spending guard or a pricing rate', async t => {
  const app = await workbench(t);
  app.input({ dataset: { match: 'max_estimated_cost_usd' }, value: '', valueAsNumber: NaN, validity: { badInput: true } });
  assert.equal(await app.exportConfig(), null);
  app.input({ dataset: { match: 'max_estimated_cost_usd' }, value: '', valueAsNumber: NaN, validity: { badInput: false } });
  assert(await app.exportConfig());
  app.input({ dataset: { role: 'SPECTRA', rate: 'input_per_million' }, value: '', valueAsNumber: NaN, validity: { badInput: true } });
  assert.equal(await app.exportConfig(), null);
});

test('cleared required numbers render safely and smoke repairs non-finite limits', async t => {
  const app = await workbench(t);
  for (const key of ['communication_rounds', 'max_attempts', 'max_output_tokens']) {
    app.input({ dataset: { match: key }, value: '', valueAsNumber: NaN });
  }
  await app.tab('live');
  assert.doesNotMatch(app.node('panel').innerHTML, /NaN|Infinity/);
  await app.tab('scenario');
  assert.doesNotMatch(app.node('panel').innerHTML, /value="NaN"/);
  await app.click('smoke');
  const config = await app.exportConfig();
  assert(config);
  assert.match(config, /max_calls = 18/);
});

test('configuration shapes reject incomplete pricing and unknown keys without TypeError', () => {
  const changes = [
    c => { c.match = null; },
    c => { c.players.SPECTRA.pricing = {}; },
    c => { c.players.SPECTRA.pricing = []; },
    c => { c.players.SPECTRA.pricing = { input_per_million: 1 }; },
    c => { c.extra = 1; },
    c => { c.match.extra = 1; },
    c => { c.players.extra = {}; },
    c => { c.players.SPECTRA.extra = 1; },
    c => { c.players.SPECTRA.pricing = { input_per_million: 1, output_per_million: 1, extra: 1 }; },
  ];
  for (const change of changes) {
    const config = structuredClone(contract.defaults);
    change(config);
    assert.throws(() => validate(config, contract), error => error instanceof Error && !(error instanceof TypeError));
  }
  const config = structuredClone(contract.defaults);
  config.match.max_estimated_cost_usd = undefined;
  assert.doesNotMatch(toml(config), /undefined/);
});

test('programmatic and missing mode/room labels remain importable without inventing live execution', async t => {
  const app = await workbench(t);
  for (const mode of ['programmatic', 'unknown', undefined]) {
    const data = structuredClone(fixture);
    data.manifest.mode = mode;
    delete data.manifest.room;
    await app.importJSON(data);
    assert.equal(app.node('status').textContent, 'Imported native run records.');
    assert.match(app.node('panel').innerHTML, /Room unspecified/);
    assert.doesNotMatch(app.node('panel').innerHTML, /LIVE API RUN/);
    assert.deepEqual(await app.exportJSON(), JSON.parse(JSON.stringify(data)));
  }
});

test('newer fixture/import intent wins over a pending mock response or error', async t => {
  const app = await workbench(t);
  for (const rejected of [false, true]) {
    let resolve, reject;
    app.io.mock = new Promise((ok, bad) => { resolve = ok; reject = bad; });
    await app.tab('offline');
    const pending = app.click('mock');
    const newer = structuredClone(fixture);
    newer.manifest.room = 'Latest selected recording';
    await app.tab('evaluation');
    await app.importJSON(newer);
    const panel = app.node('panel').innerHTML, status = app.node('status').textContent;
    if (rejected) reject(Error('Stale failure must stay hidden')); else resolve(fixture);
    await pending;
    assert.equal(app.node('panel').innerHTML, panel);
    assert.equal(app.node('status').textContent, status);
    assert.deepEqual(await app.exportJSON(), newer);
  }
});

test('mock completion after navigation leaves the active form DOM and status alone', async t => {
  const app = await workbench(t);
  let reject;
  app.io.mock = new Promise((_, bad) => { reject = bad; });
  await app.tab('offline');
  const pending = app.click('mock');
  await app.tab('scenario');
  app.node('panel').innerHTML = 'ACTIVE FORM WITH USER FOCUS';
  reject(Error('Background error'));
  await pending;
  assert.equal(app.node('panel').innerHTML, 'ACTIVE FORM WITH USER FOCUS');
  assert.equal(app.node('status').textContent, '');
});

test('failed imports reset file inputs so the same path can be retried', async t => {
  const app = await workbench(t);
  for (const id of ['json', 'directory']) {
    const target = await app.select(id, [new File(['invalid'], 'run.json')]);
    assert.equal(target.value, '');
  }
});

test('fixture HTTP errors preserve the current run and bootstrap failure is visible', async t => {
  const app = await workbench(t);
  await app.importJSON(fixture);
  app.io.fixtureError = true;
  const panel = app.node('panel').innerHTML;
  await app.click('fixture');
  assert.match(app.node('status').textContent, /Could not load/);
  assert.equal(app.node('panel').innerHTML, panel);
  assert.deepEqual(await app.exportJSON(), fixture);
});

test('contract HTTP failure displays a recoverable error without exposing controls', async t => {
  const app = await workbench(t, { contractError: true });
  assert.match(app.node('status').textContent, /Could not load the configuration contract/);
  assert.equal(app.node('nav-scenario').disabled, true);
  assert.equal(app.node('panel').innerHTML, '');
});

test('a delayed fixture cannot replace a newer imported run', async t => {
  const app = await workbench(t);
  let resolve;
  app.io.fixture = new Promise(ok => { resolve = ok; });
  const pending = app.click('fixture');
  const data = structuredClone(fixture);
  data.manifest.room = 'Newer import';
  await app.importJSON(data);
  resolve(fixture);
  await pending;
  assert.deepEqual(await app.exportJSON(), data);
});

test('empty MIME metadata keeps observations visible and corrupt PNGs are rejected', async t => {
  const app = await workbench(t);
  const files = await nativeFiles(join(root, 'example_run'));
  assert(files.filter(file => file.name.endsWith('.png')).every(file => file.type === ''));
  await app.select('directory', files);
  assert.equal((app.node('panel').innerHTML.match(/<img /g) || []).length, 21);
  const previous = await app.exportJSON();
  const invalid = files.filter(file => file.name !== 'final_spectator.png');
  invalid.push(new File(['invalid PNG'], 'final_spectator.png', { type: 'image/png' }));
  await app.select('directory', invalid);
  assert.match(app.node('status').textContent, /Invalid PNG image/);
  assert.deepEqual(await app.exportJSON(), previous);
});

test('navigation exposes its active page and status distinguishes errors', async t => {
  const app = await workbench(t);
  await app.tab('offline');
  assert.equal(app.node('nav-offline')['aria-current'], 'page');
  assert.equal(app.node('nav-evaluation')['aria-current'], undefined);
  await app.select('json', [new File(['invalid'], 'run.json')]);
  assert(app.node('status').classList.contains('warn'));
  await app.click('fixture');
  assert(!app.node('status').classList.contains('warn'));
});

function python(code, input) {
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', code], {
    cwd: root, encoding: 'utf8', timeout: 30_000, input,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, '');
  return JSON.parse(result.stdout);
}

test('configuration bounds and pricing shapes agree with Python and accepted TOML roundtrips', () => {
  const configs = [structuredClone(contract.defaults)];
  for (const key of Object.keys(contract.defaults.match)) {
    for (const value of [null, -1, 0, 0.5, 1, 2, 3, 12, 30, 256, 600, 10000, 16384, 1000000, 1000001]) {
      const config = structuredClone(contract.defaults);
      config.match[key] = value;
      configs.push(config);
    }
  }
  for (const pricing of [{}, [], { input_per_million: 1 }, { input_per_million: 1, output_per_million: 2 },
    { input_per_million: 1, output_per_million: 2, extra: 3 }]) {
    const config = structuredClone(contract.defaults);
    config.players.SPECTRA.pricing = pricing;
    configs.push(config);
  }
  for (const mutate of [c => { delete c.match; }, c => { c.match = {}; }, c => { c.match.extra = 1; },
    c => { c.extra = 1; }, c => { c.players.SPECTRA.extra = 1; }, c => { c.players.extra = {}; }]) {
    const config = structuredClone(contract.defaults); mutate(config); configs.push(config);
  }
  const cases = configs.map(config => {
    try { const normalized = validate(config, contract); return { config, accepted: true, toml: toml(normalized) }; }
    catch { return { config, accepted: false }; }
  });
  const results = python(`
import json,sys,tempfile
from pathlib import Path
from parallax_relay.config import GameConfig,load_config
results=[]
for case in json.load(sys.stdin):
    try:
        config=GameConfig.model_validate(case['config']); accepted=True
    except ValueError:
        accepted=False
    if case['accepted']:
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.toml';path.write_text(case['toml'],encoding='utf-8')
            assert path.read_text(encoding='utf-8')==case['toml']
            assert load_config(path)==config
    results.append(accepted)
print(json.dumps(results))
`, JSON.stringify(cases));
  assert.deepEqual(cases.map(item => item.accepted), results);
});

test('live approval requires a guard/rates and resets after every editable setting changes', async t => {
  const app = await workbench(t);
  await app.tab('live'); await app.click('approve');
  assert.match(app.node('status').textContent, /spending guard/);
  app.input({ dataset: { match: 'max_estimated_cost_usd' }, value: '1', valueAsNumber: 1 });
  await app.click('approve'); assert.match(app.node('status').textContent, /pricing/);
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) for (const rate of ['input_per_million', 'output_per_million']) {
    app.input({ dataset: { role, rate }, value: '1', valueAsNumber: 1 });
  }
  const edits = Object.keys(contract.defaults.match).map(key => ({ dataset: { match: key },
    value: key === 'condition' ? '' : String(key === 'max_estimated_cost_usd' ? 1 : contract.defaults.match[key]),
    valueAsNumber: key === 'max_estimated_cost_usd' ? 1 : contract.defaults.match[key] }));
  for (const role of ['SPECTRA', 'PYRA', 'FLUX']) {
    for (const key of ['provider', 'model_env', 'api_key_env']) edits.push({ dataset: { role, player: key }, value: contract.defaults.players[role][key] });
    for (const rate of ['input_per_million', 'output_per_million']) edits.push({ dataset: { role, rate }, value: '1', valueAsNumber: 1 });
  }
  for (const edit of edits) {
    await app.click('approve'); assert.match(app.node('panel').innerHTML, /Download approved TOML/);
    app.input(edit);
    const count = app.downloads.length;
    await app.click('approved-download'); assert.equal(app.downloads.length, count);
  }
});

test('model text and non-PNG image references remain data', async t => {
  const app = await workbench(t);
  const data = structuredClone(fixture), text = '<img src=x onerror="alert(1)">';
  data.manifest.room = text;
  data.replay[0].communications[0].text = text;
  data.replay[0].events = [text, { nested: text }];
  data.calls[0].status = text;
  data.images[data.replay[0].observations.SPECTRA.image] = 'https://invalid.example/tracker.png';
  await app.importJSON(data);
  assert.equal(app.node('status').textContent, 'Imported native run records.');
  assert.doesNotMatch(app.node('panel').innerHTML, /<img src=x|src="https:/);
  assert.match(app.node('panel').innerHTML, /&lt;img src=x/);
  assert.equal(Object.prototype.polluted, undefined);
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

test('actual programmatic v3 Recorder binds room and rejects invalid embedded geometry', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'parallax-programmatic-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const output = join(directory, 'run');
  python(`
import asyncio,json,sys
from pathlib import Path
from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import run_match
from parallax_relay.protocol import ROLES
from parallax_relay.recording import Recorder
out=Path(json.load(sys.stdin))
recorder=Recorder(out,{'schema_version':2,'mode':'programmatic'})
asyncio.run(run_match({r:ScriptedAgent(r) for r in ROLES},MatchSettings(max_turns=1),recorder=recorder))
print('{}')
`, JSON.stringify(output));
  const app = await workbench(t);
  await app.select('directory', await nativeFiles(output));
  assert.equal(app.node('status').textContent, 'Imported native run records.');
  const exported = await app.exportJSON();
  assert.equal(exported.manifest.mode, 'programmatic');
  assert.equal(exported.manifest.room, 'split_span');
  const bad=structuredClone(exported);bad.final_state.robots.SPECTRA.x=99;
  assert.throws(()=>checkRun(bad),/room|position|state/);
  const mismatched=structuredClone(exported);mismatched.manifest.provenance.inputs.room.value.definition.id='other';
  assert.throws(()=>checkRun(mismatched),/room/);
  const mutations=[
   d=>{d.manifest.provenance.inputs.room.value.definition.bridges[0].gap=[];},
   d=>{d.final_state.loss=true;},
   d=>{d.final_state.motor_heat=99;},
   d=>{d.manifest.provenance.inputs.room.value.definition.bridges[0].gap=[5,7];},
   d=>{d.manifest.provenance.inputs.room.value.definition.cells=[5];},
   d=>{d.manifest.provenance.inputs.room.value.definition.starts=[2,3,99];},
   d=>{d.final_state.collected_cells=[10];},
  ];
  for(const mutate of mutations){
   const broken=structuredClone(exported);mutate(broken);
   assert.throws(()=>checkRun(broken),/room|state|loss|alias|gap|position|cell|bridge/);
   await app.importJSON(broken);assert.deepEqual(await app.exportJSON(),exported);
  }

  assert.match(app.node('panel').innerHTML, /split_span · programmatic/);
});


test('external-result v3 records preserve unknown execution and validate all nine recorded room definitions',async t=>{
 const directory=await mkdtemp(join(tmpdir(),'parallax-external-rooms-'));
 t.after(()=>rm(directory,{recursive:true,force:true}));
 const runs=python(`
import json,sys
from pathlib import Path
from parallax_relay.rooms import rooms
from parallax_relay.state import initial_world
from parallax_relay.budget import Budget
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import MatchResult
from parallax_relay.recording import Recorder
root=Path(json.load(sys.stdin));runs=[]
for room in rooms():
 out=root/room.id
 result=MatchResult(initial_world(room.id),'turn_limit',[],[],Budget(MatchSettings(),{}).summary())
 Recorder(out,{}).finish(result)
 runs.append({**{k:json.loads((out/(k+'.json')).read_text()) for k in ('manifest','result','final_state')},'calls':[],'phases':[],'replay':[]})
print(json.dumps(runs))
`,JSON.stringify(directory));
 const app=await workbench(t);
 for(const run of runs){
  assert.equal(run.manifest.provenance.execution,null);
  assert.equal(run.manifest.provenance.lifecycle.started_at,null);
  checkRun(run);await app.importJSON(run);assert.deepEqual(await app.exportJSON(),run);
 }
});
