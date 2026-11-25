import {Scene, ROLES, COLORS} from './scene.js';
import {Manual} from './manual.js';
import {StagePresentation} from './presentation.js';

const byId = id => document.getElementById(id);
const modeLabels = {
  reactive: 'Reactive offline controller', manual: 'Manual offline control', test: 'Offline HTTP adapter test',
  live: 'Live model run', baseline: 'Turn-based baseline · scripted offline',
};
const roleNames = {SPECTRA: 'Optical', PYRA: 'Thermal', FLUX: 'Circuit'};
const phaseNames = {broadcast: 'Broadcast', negotiate: 'Negotiate', commit: 'Commit'};
const scene = new Scene();
new StagePresentation(scene);
const manual = new Manual(post);
const feeds = new Map();
const groups = new Map();
const speechHistory = [];
const speechReader = byId('speech-reader');
const readSpeech = byId('read-speech');
let speechIndex = -1;
const announced = new Set();
const announcementQueue = [];
const cards = new Map();
let token = null, runID = '', cursor = 0, mode = '', status = 'idle', phase = '', windowNumber = 0;
let dialogueTotal = 0, currentGroup = null, speechGroup = '', connected = false, startedHere = false;
let feedGeneration = 0, feedKey = '', imageURL = '', announcementTimer = 0;
let controlPending = '', restartAvailable = false;
let recordingFailed = false;

function make(tag, parent, text = '') {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  parent.append(el);
  return el;
}

function setText(id, value) {
  const element = byId(id);
  const text = String(value);
  if (element.textContent !== text) element.textContent = text;
}

function words(value) { return typeof value === 'string' ? value.replaceAll('_', ' ') : ''; }
function sourceLabel(data) {
  const source = typeof data === 'string' ? data : data?.source;
  const names = {reactive_local: 'reactive controller', manual: 'manual', offline_test_transport: 'offline HTTP test',
    scripted_fixture: 'scripted fixture', live_model: 'live model'};
  return [names[source] || words(source), data?.model].filter(item => typeof item === 'string' && item).join(' · ');
}

for (const role of ROLES) {
  const card = make('div', byId('team'));
  card.className = 'role-card';
  const portrait = make('span', card);
  portrait.className = 'portrait';
  portrait.setAttribute('aria-hidden', 'true');
  // The full master is always available, even when optional animation sheets are absent.
  portrait.style.backgroundImage = 'url("/art/' + role.toLowerCase() + '-idle.png")';
  portrait.style.backgroundSize = '118% auto'; portrait.style.backgroundPosition = '50% 43%';
  const title = make('div', card);
  make('div', title, role).className = 'role-name';
  const source = make('span', title, roleNames[role]);
  source.className = 'role-source';
  const ready = make('span', card, 'Pending');
  ready.className = 'readiness'; ready.dataset.ready = role;
  cards.set(role, {source, ready});
}

function setReady(role, disposition) {
  const ready = cards.get(role)?.ready;
  if (!ready) return;
  const state = ['ready', 'ok', 'accepted', 'sealed', 'valid'].includes(disposition) ? 'ready' : disposition === 'pending' ? 'pending' : 'fallback';
  ready.dataset.state = state;
  ready.textContent = state === 'ready' ? '✓ Ready' : state === 'pending' ? '· Pending' : '◇ Fallback';
  ready.setAttribute('aria-label', role + ' ' + state);
  ready.title = words(disposition);
}

function configure(data) {
  if (typeof data.mode === 'string') mode = data.mode;
  scene.baseline = mode === 'baseline';
  setText('terrain-description', scene.baseline ? 'A flat lane from columns 0 to 12. Powering the bridge connects columns 5–7.' :
    'A gap separates the banks at columns 5–7. Powering the bridge extends its deck at height zero. The far bank starts at column 7.5, half a tile higher.');
  setText('goal-description', scene.baseline ? 'Unlock the exit and bring all three robots to extraction.' :
    'Power the bridge, recover the shard, then bring all three robots to the raised exit at column 12, grounded.');
  const room = typeof data.room === 'string' ? data.room : data.room?.name;
  if (room) {
    const label = /split.?span|dev.?bridge|(?:physical|physics).*bridge|bridge.*(?:room|v1)/i.test(room) ? 'The Split Span' : words(room);
    setText('scene-heading', label);
  }
  setText('source', modeLabels[mode] || words(mode) || 'Local match');
  manual.configure(mode, data);
  for (const role of ROLES) {
    const source = data.sources?.[role] ?? data.players?.[role]?.source;
    if (source) cards.get(role).source.textContent = roleNames[role] + ' · ' + sourceLabel(source);
  }
  startControl();
}

function startControl() {
  const start = byId('start');
  const canStart = status === 'idle' && mode !== 'live';
  const canRestart = status !== 'idle' && restartAvailable;
  start.disabled = !connected || Boolean(controlPending) || !(canStart || canRestart);
  const label = controlPending || (canRestart ? 'Restart Match' : canStart ? 'Start match' :
    status === 'ended' ? 'Match ended' : status === 'running' ? 'Match running' : 'Waiting for launcher');
  if (start.firstChild.nodeValue !== label + ' ') start.firstChild.nodeValue = label + ' ';
  start.querySelector('span').hidden = !canStart || Boolean(controlPending);
}

function connection(state) {
  if (byId('connection').dataset.state === state) return;
  connected = state === 'connected';
  byId('connection').dataset.state = state;
  setText('connection', connected ? 'Connected' : state === 'connecting' ? 'Connecting' : 'Reconnecting');
  scene.setConnected(connected && status !== 'ended');
  manual.online = connected;
  manual.refresh();
  startControl();
}

async function request(path, options = {}) {
  const headers = {...options.headers};
  if (path !== '/api/status') headers['X-Relay-Token'] = token;
  const response = await fetch(path, {cache: 'no-store', ...options, headers});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.error === 'string' ? body.error : 'Request failed (' + response.status + ').');
    error.status = response.status;
    throw error;
  }
  return response;
}

async function post(path, value) {
  const response = await request(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
  return response.json();
}

function clearFeed() {
  feedGeneration++;
  feedKey = '';
  const img = byId('sensor-image');
  img.onload = img.onerror = null;
  img.removeAttribute('src'); img.alt = ''; img.hidden = true;
  if (imageURL) { URL.revokeObjectURL(imageURL); imageURL = ''; }
}

async function showFeed() {
  const role = byId('sensor-select').value;
  const spectator = role === 'SPECTATOR';
  byId('stage-viewport').hidden = byId('stage-controls').hidden = !spectator;
  byId('room-guide').hidden = !spectator;
  byId('sensor-view').hidden = spectator;
  scene.zoom.hidden = !spectator || !scene.usesManualPan();
  if (spectator) {
    if (feedKey || imageURL) clearFeed();
    scene.paint(true);
    return;
  }
  const sample = feeds.get(role);
  const key = runID + '/' + role + '/' + (sample?.window ?? '');
  if (key === feedKey) return;
  clearFeed(); feedKey = key;
  const generation = feedGeneration;
  if (!sample) { setText('sensor-caption', 'Waiting for a sampled ' + role + ' observation.'); return; }
  const label = role + ' · ' + roleNames[role] + ' sensor · Window ' + sample.window + ' · Sampled at tick ' + sample.tick;
  setText('sensor-caption', 'Loading ' + label);
  try {
    const response = await request('/api/feed/' + role + '/' + sample.window,
      {headers: {'X-Relay-Run-ID': runID}});
    const description = response.headers.get('X-Relay-Sensor-Description');
    const blob = await response.blob();
    if (generation !== feedGeneration) return;
    const url = URL.createObjectURL(blob), img = byId('sensor-image');
    imageURL = url;
    img.onload = () => {
      if (generation !== feedGeneration) return;
      img.hidden = false;
      setText('sensor-caption', label);
    };
    img.onerror = () => { if (generation === feedGeneration) setText('sensor-caption', label + ' · Image unavailable.'); };
    img.alt = role + ' original sensor observation for window ' + sample.window + (description ? '. ' + description : '');
    img.src = url;
  } catch {
    if (generation === feedGeneration) setText('sensor-caption', label + ' · Image unavailable.');
  }
}

function pumpAnnouncements() {
  if (announcementTimer || !announcementQueue.length) return;
  setText('announcements', announcementQueue.shift());
  announcementTimer = setTimeout(() => { announcementTimer = 0; pumpAnnouncements(); }, 600);
}

function announceGroup(group, historical) {
  if (!group || announced.has(group.key)) return;
  announced.add(group.key);
  if (historical) return;
  announcementQueue.push(group.title + '. ' + group.lines.join('. '));
  pumpAnnouncements();
}

function updateSpeechNavigation() {
  byId('speech-previous').setAttribute('aria-disabled', String(speechIndex <= 0));
  byId('speech-next').setAttribute('aria-disabled', String(speechIndex >= speechHistory.length - 1));
}

function readMessage(index) {
  const entry = speechHistory[index];
  if (!entry) return;
  speechIndex = index;
  const label = byId('speech-reader-label');
  label.style.setProperty('--role-color', COLORS[entry.role]);
  label.textContent = entry.role + ' · ' + entry.title;
  const text = byId('speech-reader-text');
  text.textContent = entry.text;
  text.scrollTop = 0;
  updateSpeechNavigation();
}

readSpeech.addEventListener('click', () => {
  if (!speechHistory.length) return;
  readMessage(speechHistory.length - 1);
  speechReader.showModal();
});
byId('speech-previous').addEventListener('click', () => readMessage(speechIndex - 1));
byId('speech-next').addEventListener('click', () => readMessage(speechIndex + 1));

function dialogue(event, historical) {
  if (!ROLES.includes(event.role) || typeof event.text !== 'string' || !event.text.trim()) return;
  const stage = phaseNames[event.phase] ? event.phase : phase;
  const key = event.window + '/' + stage;
  if (currentGroup?.key !== key) announceGroup(currentGroup, historical);
  let group = groups.get(key);
  if (!group) {
    const section = make('section', byId('transcript'));
    const title = 'Window ' + event.window + ' · ' + (phaseNames[stage] || 'Public dialogue');
    make('h3', section, title);
    group = {key, title, section, lines: []};
    groups.set(key, group);
  }
  currentGroup = group;
  const row = make('article', group.section);
  row.dataset.seq = event.seq; row.dataset.role = event.role; row.dataset.tick = event.tick;
  const label = make('div', row);
  label.className = 'log-meta';
  const speaker = make('b', label, event.role);
  speaker.style.setProperty('--role-color', COLORS[event.role]);
  label.append(document.createTextNode(' · Tick ' + event.tick + (event.source ? ' · ' + sourceLabel(event.source) : '')));
  make('p', row, event.text);
  speechHistory.push({role: event.role, text: event.text, title: group.title});
  readSpeech.disabled = false;
  if (speechReader.open) updateSpeechNavigation();
  group.lines.push(event.role + '. ' + event.text);
  if (group.lines.length === ROLES.length) announceGroup(group, historical);
  setText('dialogue-count', ++dialogueTotal + (dialogueTotal === 1 ? ' message' : ' messages'));
  byId('dialogue-empty').hidden = true;
  if (speechGroup !== key) { scene.speech.clear(); speechGroup = key; }
  scene.say(event.role, event.text, event.seq);
}

function describeAction(action) {
  if (!action || typeof action.kind !== 'string') return 'Unavailable';
  if (action.kind === 'MOVE') return 'Move ' + (action.direction === -1 ? 'left' : 'right') + ' ' + action.steps + (action.steps === 1 ? ' tile' : ' tiles');
  if (action.kind === 'RUN') return 'Run ' + (action.direction === -1 ? 'left' : 'right') + ' for ' + action.ticks +
    ' ticks' + (action.jump_at == null ? '' : ', jump at +' + action.jump_at);
  if (action.kind === 'WAIT') return Number.isInteger(action.ticks) ? 'Wait ' + action.ticks + (action.ticks === 1 ? ' tick' : ' ticks') : 'Wait';
  return words(action.kind).toLowerCase();
}

function released(event) {
  const details = byId('released-plans'), list = details.querySelector('ul');
  list.replaceChildren();
  const planMap = event.plans;
  if (planMap && typeof planMap === 'object') {
    for (const role of ROLES) {
      const plan = planMap[role];
      let label = 'Neutral';
      if (Array.isArray(plan) && plan.length) label = plan.map(describeAction).join(' → ');
      else if (plan && typeof plan.kind === 'string') label = describeAction(plan);
      make('li', list, role + ' · ' + label);
    }
  }
  details.hidden = !list.children.length;
  details.querySelector('summary').textContent = 'Released plans · Window ' + event.window + ' · Tick ' + (event.start_tick ?? event.tick);
}

function consequence(event) {
  if (typeof event.text !== 'string' || !event.text) return;
  const item = document.createElement('li');
  item.dataset.seq = event.seq; item.dataset.tick = event.tick; item.dataset.eventKind = event.event_kind || 'event';
  const meta = make('span', item, 'Window ' + event.window + ' · Tick ' + event.tick);
  meta.className = 'log-meta';
  make('p', item, event.text);
  byId('consequences').prepend(item);
  byId('events-empty').hidden = true;
  scene.contact(event);
}

function updateWorld(world) {
  if (!world) return;
  scene.setWorld(world);
  if (Number.isSafeInteger(world.tick)) setText('tick', world.tick);
  if (typeof world.bridge_powered === 'boolean') setText('bridge', world.bridge_powered ? 'Powered' : 'Retracted');
  if (typeof world.exit_unlocked === 'boolean') setText('exit-state', world.exit_unlocked ? 'Unlocked' : 'Locked');
}

function eventRow(event, historical) {
  if (['phase_open', 'window_started', 'checkpoint'].includes(event.kind) && Number.isSafeInteger(event.window) && event.window > 0) {
    windowNumber = event.window; setText('window', windowNumber);
  }
  if (Number.isSafeInteger(event.tick)) setText('tick', event.tick);
  switch (event.kind) {
    case 'match':
      configure(event);
      if (event.world) updateWorld(event.world);
      break;
    case 'phase_open':
      announceGroup(currentGroup, historical);
      currentGroup = null;
      phase = event.phase; status = 'running';
      setText('phase', phaseNames[phase] || words(phase));
      setText('team-caption', phase === 'commit' ? 'Collecting sealed plans' : 'Public discussion');
      if (phase !== 'commit') manual.close(event.window, 'Waiting for the next commit phase.');
      for (const role of ROLES) setReady(role, 'pending');
      break;
    case 'manual_request': manual.request(event); break;
    case 'phase_closed':
      if (currentGroup && event.phase === phase) { announceGroup(currentGroup, historical); currentGroup = null; }
      break;
    case 'ready':
      setReady(event.role, event.disposition);
      manual.ready(event.role, event.disposition, words(event.status));
      break;
    case 'observation':
      if (ROLES.includes(event.role)) feeds.set(event.role, {window: event.window, tick: event.tick});
      break;
    case 'dialogue': dialogue(event, historical); break;
    case 'window_started':
      announceGroup(currentGroup, historical); currentGroup = null;
      phase = 'action'; status = 'running';
      setText('phase', scene.baseline ? 'Turn resolution' : 'In motion');
      setText('team-caption', 'Shared start · Tick ' + (event.start_tick ?? event.tick));
      manual.close(event.window, 'Programs have started.');
      released(event);
      break;
    case 'state': updateWorld(event.world); break;
    case 'checkpoint':
      updateWorld(event.world); phase = 'checkpoint';
      setText('phase', 'Checkpoint');
      setText('team-caption', 'Window ' + event.window + ' ended · Tick ' + event.tick);
      break;
    case 'consequence': consequence(event); break;
    case 'result':
      announceGroup(currentGroup, historical); currentGroup = null;
      status = 'ended'; phase = 'ended'; setText('phase', 'Finished');
      setText('team-caption', 'Match ended');
      manual.close(event.window, 'The match has ended.');
      if (event.world) updateWorld(event.world);
      setText('result', (event.completed ? 'Checkpoint complete' : 'Run stopped') + ' · ' + (words(event.stop_reason) || 'Reason unavailable') + ' · Tick ' + event.tick);
      byId('result').dataset.error = 'false'; byId('result').hidden = false; scene.setConnected(false);
      break;
  }
}

function resetPage() {
  cursor = 0; windowNumber = 0; phase = ''; dialogueTotal = 0; currentGroup = null; speechGroup = '';
  recordingFailed = false;
  groups.clear(); feeds.clear(); announced.clear(); announcementQueue.length = 0;
  if (speechReader.open) speechReader.close();
  speechHistory.length = 0; speechIndex = -1; readSpeech.disabled = true;
  setText('speech-reader-label', ''); setText('speech-reader-text', '');
  clearTimeout(announcementTimer); announcementTimer = 0;
  clearFeed(); scene.reset(); manual.close(0, '', true);
  byId('transcript').replaceChildren(); byId('consequences').replaceChildren();
  byId('dialogue-empty').hidden = byId('events-empty').hidden = false;
  byId('result').hidden = byId('released-plans').hidden = true;
  byId('released-plans').querySelector('ul').replaceChildren();
  setText('announcements', ''); setText('dialogue-count', ''); setText('phase', 'Ready to start');
  setText('team-caption', 'Awaiting the match'); setText('window', '—'); setText('tick', '—');
  setText('bridge', '—'); setText('exit-state', '—');
  for (const role of ROLES) setReady(role, 'pending');
}

function applyPage(page, replay) {
  if (!page || typeof page.run_id !== 'string' || !Number.isSafeInteger(page.cursor) || !Array.isArray(page.events)) {
    throw new Error('Invalid journal response.');
  }
  if (runID && page.run_id !== runID || page.cursor < cursor) { resetPage(); replay = true; }
  if (page.reset) replay = true;
  runID = page.run_id;
  setText('run-id', 'Run ' + runID);
  const unseen = page.events.filter(row => Number.isSafeInteger(row.seq) && row.seq > cursor);
  let last = cursor;
  for (const event of unseen) {
    // The server retains every semantic event and coalesces superseded poses.
    if (event.seq <= last || event.run_id && event.run_id !== runID) throw new Error('Journal sequence changed.');
    last = event.seq;
  }
  if (page.cursor < last || page.has_more && page.cursor <= cursor) throw new Error('Journal cursor changed.');
  scene.batching = true; scene.historical = replay;
  try { for (const event of unseen) eventRow(event, replay); }
  finally { scene.batching = false; scene.historical = false; }
  if (replay) scene.cues.clear();
  cursor = page.cursor; setText('journal-seq', cursor);
  if (unseen.length) {
    scene.releaseSpeech();
    if (byId('sensor-select').value !== 'SPECTATOR') void showFeed();
    startControl();
  }
  // A failed final write cannot append a result to its own journal.
  if (page.recording_error === true && !page.has_more && !recordingFailed) {
    recordingFailed = true; status = 'ended'; phase = 'ended';
    updateWorld(page.last_recorded_world);
    scene.cues.clear(); scene.setConnected(false);
    manual.close(windowNumber, 'The recording failed.');
    setText('phase', 'Finished'); setText('team-caption', 'Match ended');
    const tick = byId('tick').textContent;
    setText('result', 'Recording failed · last recorded tick ' + (tick === '—' ? 'unavailable' : tick));
    byId('result').dataset.error = 'true'; byId('result').hidden = false;
    startControl();
  }
}

byId('sensor-select').addEventListener('change', showFeed);
document.addEventListener('visibilitychange', () => { if (!document.hidden) scene.paint(true); });
byId('start').addEventListener('click', async () => {
  if (byId('start').disabled) return;
  const restarting = status !== 'idle';
  controlPending = restarting ? 'Restarting…' : 'Starting…';
  startControl();
  byId('start-feedback').hidden = true;
  try {
    await post(restarting ? '/api/restart' : '/api/start', restartAvailable ? {run_id: runID} : {});
    if (restarting) {
      // Reload the room on the same URL so old drafts and in-flight reads are discarded.
      window.location.reload();
      return;
    }
    startedHere = true;
    if (status !== 'ended') status = 'running';
    byId('scene-heading').focus({preventScroll: true});
  } catch (error) {
    setText('start-feedback', error.message);
    byId('start-feedback').hidden = false;
  }
  controlPending = ''; startControl();
});

let backoff = 90, reconnecting = false, boot = true, rebuilding = false;
async function poll() {
  try {
    if (!token) {
      const info = await (await request('/api/status')).json();
      if (typeof info.token !== 'string' || !info.token) throw new Error('Session unavailable.');
      token = info.token;
      restartAvailable = info.restart_available === true;
      if (runID && info.run_id !== runID) { resetPage(); startedHere = false; }
      status = info.status || 'idle'; runID = info.run_id || '';
      configure(info);
    }
    const page = await (await request('/api/events?after=' + cursor)).json();
    if (runID && typeof page.run_id === 'string' && page.run_id !== runID) {
      window.location.reload();
      return;
    }
    rebuilding ||= Boolean(page.reset) || reconnecting || (boot && status !== 'idle' && !startedHere);
    applyPage(page, rebuilding);
    if (page.has_more) { backoff = 0; return; }
    connection('connected');
    if (reconnecting && byId('sensor-select').value !== 'SPECTATOR') { clearFeed(); void showFeed(); }
    backoff = status === 'ended' ? 1800 : status === 'idle' ? 200 : 65;
    reconnecting = false; boot = false; rebuilding = false;
  } catch (error) {
    reconnecting = true;
    if (error.status === 403) token = null;
    if (error.message === 'Journal sequence changed.' || error.message === 'Journal cursor changed.') {
      resetPage(); token = null;
    }
    connection(cursor || !boot ? 'reconnecting' : 'connecting');
    backoff = Math.min(Math.max(180, backoff * 1.6), 2400);
  } finally { setTimeout(poll, backoff); }
}
poll();
