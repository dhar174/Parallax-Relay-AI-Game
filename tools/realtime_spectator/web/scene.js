export const ROLES = ['SPECTRA', 'PYRA', 'FLUX'];
export const COLORS = {SPECTRA: '#31547b', PYRA: '#86411c', FLUX: '#006557'};
const FRAME_COUNT = {idle: 4, walk: 6, jump: 4};
const JUMP_FRAME = {takeoff: 0, ascent: 1, descent: 2, landing: 3};
const STATIC_CROPS = {
  floor: [300, 199, 1573, 318], bridge: [299, 197, 1575, 358],
  'motor-console': [340, 117, 625, 954], 'memory-shard': [554, 142, 430, 718],
  'energy-cell': [289, 270, 527, 868], 'exit-open': [162, 176, 810, 1020],
  'exit-closed': [162, 176, 810, 1020],
};
// Source masters have different transparent margins from the 256-pixel atlases.
const STATIC_FEET = {SPECTRA: [585, 1158, 1090], PYRA: [600, 1136, 967], FLUX: [591, 1150, 1101]};
const clamp = (value, low, high) => Math.max(low, Math.min(value, high));
const finite = Number.isFinite;
const BUBBLE_INSET = 6;
const BUBBLE_GAP = 5;
const WORDS_PER_MINUTE = 160;
const ROOM = {left: -.95, right: 12.95, bottom: -2.25, top: 3.5};

function cameraCenter(value, span, min, max) {
  return span >= max - min ? (min + max) / 2 : clamp(value, min + span / 2, max - span / 2);
}

function cameraFrame(width, height, tile, x, y) {
  const cx = cameraCenter(x, width / tile, ROOM.left, ROOM.right);
  const cy = cameraCenter(y, height / tile, ROOM.bottom, ROOM.top);
  return {tile, originX: width / 2 - cx * tile, originY: height / 2 + cy * tile};
}

function containsRobot(frame, width, height, x, y) {
  const footX = frame.originX + x * frame.tile;
  const footY = frame.originY - y * frame.tile;
  return footX >= frame.tile * .44 && footX <= width - frame.tile * .44 &&
    footY >= frame.tile * .84 && footY <= height;
}

function make(tag, className, parent) {
  const node = document.createElement(tag);
  node.className = className;
  parent.append(node);
  return node;
}

function readingDuration(text) {
  const words = text.match(/\S+/gu) || [];
  const units = words.reduce((total, word) => total + Math.ceil(Array.from(word).length / 16), 0);
  return Math.max(2000, units * 60_000 / WORDS_PER_MINUTE);
}

// The same function can take elapsed time and duration from a future audio player.
function advanceMessage(message, elapsedMs, durationMs) {
  const remaining = message.scrollHeight - message.clientHeight;
  if (remaining <= 0) return false;
  const lineHeight = parseFloat(getComputedStyle(message).lineHeight);
  const steps = Math.ceil(remaining / lineHeight);
  const line = Math.floor(elapsedMs / durationMs * (steps + 1));
  message.scrollTop = Math.min(remaining, line * lineHeight);
  return line < steps;
}

function bubbleBox(head, width, height, view, placed) {
  const min = BUBBLE_INSET;
  const maxX = view.width - width - min, maxY = view.height - height - min;
  const gap = BUBBLE_GAP;
  const naturalX = clamp(head.x - width / 2, min, maxX);
  const naturalY = clamp(head.y - height - 8, min, maxY);
  const xs = [naturalX, min, maxX, ...placed.flatMap(box => [box.left - width - gap, box.right + gap])];
  const ys = [naturalY, min, maxY, head.y + 10, ...placed.flatMap(box => [box.top - height - gap, box.bottom + gap])];
  let best, bestCost = Infinity;
  for (const x of xs) {
    for (const y of ys) {
      const left = clamp(x, min, maxX), top = clamp(y, min, maxY);
      const right = left + width, bottom = top + height;
      if (placed.some(box => left < box.right + gap && right > box.left - gap &&
          top < box.bottom + gap && bottom > box.top - gap)) continue;
      const cost = Math.abs(left - naturalX) + Math.abs(top - naturalY);
      if (cost < bestCost) { bestCost = cost; best = {left, top, right, bottom}; }
    }
  }
  return best;
}

export class Scene {
  constructor() {
    this.stage = document.querySelector('#stage');
    this.stageShell = document.querySelector('#stage-shell');
    this.scroll = document.querySelector('#stage-scroll');
    this.zoom = document.querySelector('#zoom');
    this.bubbleLayer = document.querySelector('#bubbles');
    this.canvas = document.querySelector('#scenery');
    this.context = this.canvas.getContext('2d');
    this.actors = {};
    this.assets = new Map();
    this.world = null;
    this.baseline = false;
    this.connected = false;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)');
    this.speech = new Map();
    this.speechTimer = 0;
    this.speechPausedAt = null;
    this.speechPausedTotal = 0;
    this.pauseButton = document.querySelector('#speech-pause');
    this.positionText = new Map();
    this.cues = new Map();
    this.batching = false;
    this.frame = 0;
    this.lastPaint = 0;
    this.historical = false;
    this.presentation = '';
    this.followRole = null;
    this.followCenter = null;
    this.projectedFrame = null;
    this.cameraAnimation = 0;
    this.manualEnlarged = false;
    this.manualPan = 0;
    for (const key of Object.keys(STATIC_CROPS)) this.load(key, '/art/' + key + '.png');
    for (const role of ROLES) {
      const slug = role.toLowerCase();
      this.load(slug, '/art/' + slug + '-idle.png');
      for (const action of Object.keys(FRAME_COUNT)) {
        const key = slug + '-' + action;
        this.load(key, '/art/animations/sheets/' + key + '.png', FRAME_COUNT[action]);
      }
      const mark = make('div', 'actor', document.querySelector('#actors'));
      mark.dataset.robot = role;
      const art = make('span', 'robot-art', mark);
      const leader = make('span', 'leader', this.bubbleLayer);
      leader.style.setProperty('--role-color', COLORS[role]);
      const bubble = make('div', 'bubble', this.bubbleLayer);
      bubble.dataset.bubble = role;
      bubble.style.setProperty('--role-color', COLORS[role]);
      const speaker = make('b', 'bubble-speaker', bubble);
      speaker.textContent = role;
      const message = make('span', 'bubble-message', bubble);
      message.dir = 'auto';
      message.hidden = true;
      this.actors[role] = {mark, art, leader, bubble, message};
      mark.hidden = bubble.hidden = leader.hidden = true;
    }
    this.resize = new ResizeObserver(() => this.paint(true));
    this.resize.observe(this.stage);
    this.resize.observe(this.scroll);
    this.reduced.addEventListener('change', () => {
      this.setSpeechPaused(this.reduced.matches);
      this.paint(true);
    });
    this.setSpeechPaused(this.reduced.matches);
    this.pauseButton.addEventListener('click', () => this.setSpeechPaused(this.speechPausedAt === null));
    document.querySelector('#speech-size').addEventListener('change', event => {
      this.stageShell.dataset.speechSize = event.target.value;
      this.paint(true);
    });
    this.scroll.addEventListener('scroll', () => this.paint(true), {passive: true});
    this.zoom.addEventListener('click', () => {
      this.manualEnlarged = !this.manualEnlarged;
      this.manualPan = 0;
      this.syncPan();
      this.paint(true);
    });
    document.querySelector('#stage-camera').addEventListener('change', event => {
      const role = event.target.value;
      this.setFraming(this.presentation, ROLES.includes(role) ? role : null);
    });
  }

  usesManualPan() {
    return !this.presentation && !this.followRole;
  }

  syncPan() {
    const manual = this.usesManualPan();
    const enlarged = manual && this.manualEnlarged;
    this.zoom.hidden = !manual;
    this.zoom.setAttribute('aria-pressed', String(enlarged));
    this.zoom.textContent = enlarged ? 'Room overview' : 'Enlarge room';
    this.scroll.classList.toggle('enlarged', enlarged);
    this.scroll.setAttribute('aria-label', enlarged ? 'Enlarged room. Use arrow keys to pan.' :
      this.followRole ? `Following ${this.followRole}` : 'Room overview');
    this.scroll.scrollLeft = enlarged ? this.manualPan : 0;
  }

  setFraming(presentation, followRole) {
    if (this.usesManualPan()) this.manualPan = this.scroll.scrollLeft;
    this.presentation = presentation;
    this.followRole = followRole;
    this.followCenter = null;
    if (presentation) this.stageShell.dataset.presentation = presentation;
    else delete this.stageShell.dataset.presentation;
    this.syncPan();
    this.paint(true);
  }

  setPresentation(mode) {
    this.setFraming(mode, this.followRole);
  }

  load(key, path, frames) {
    const image = new Image();
    image.onload = () => {
      if (frames && (image.naturalWidth !== frames * 256 || image.naturalHeight !== 256)) return;
      this.assets.set(key, image);
      this.paint(true);
    };
    image.src = path;
  }

  reset() {
    this.world = null;
    this.followCenter = null;
    this.projectedFrame = null;
    cancelAnimationFrame(this.cameraAnimation);
    this.cameraAnimation = 0;
    this.speech.clear();
    this.releaseSpeech();
    this.cues.clear();
    this.stage.removeAttribute('data-tick');
    document.querySelector('#await-scene').hidden = false;
    document.querySelector('#scene-description').textContent = 'Waiting for the first world sample.';
    this.positionText.clear();
    const awaiting = document.createElement('li');
    awaiting.textContent = 'Waiting for the first world sample.';
    document.querySelector('#room-positions').replaceChildren(awaiting);
    for (const actor of Object.values(this.actors)) {
      actor.mark.hidden = actor.leader.hidden = actor.bubble.hidden = true;
    }
    this.paint(true);
  }

  setWorld(world) {
    if (!world || !ROLES.every(role => finite(world.robots?.[role]?.x) && finite(world.robots[role].y))) return;
    this.world = world;
    this.stage.dataset.tick = world.tick;
    document.querySelector('#await-scene').hidden = true;
    const positions = document.querySelector('#room-positions');
    if (!this.positionText.size) {
      positions.replaceChildren();
      for (const role of ROLES) this.positionText.set(role, make('li', '', positions));
    }
    document.querySelector('#scene-description').textContent = ROLES.map(role => {
      const r = world.robots[role];
      const description = role + ' at column ' + (r.x / 256).toFixed(1) + ', height ' + (r.y / 256).toFixed(1) +
        ' tiles, ' + (r.grounded ? 'grounded' : 'airborne') + ', ' + r.pose;
      this.positionText.get(role).textContent = description + '.';
      return description;
    }).join('. ') + '.';
    this.paint(true);
  }

  contact(event) {
    const role = event.role;
    if (!this.world || !ROLES.includes(role) || !finite(event.x) || !finite(event.y)) return;
    const robot = {...this.world.robots[role]};
    for (const key of ['x', 'y', 'vx', 'vy', 'facing', 'grounded', 'pose']) {
      if (event[key] !== undefined) robot[key] = event[key];
    }
    if (this.world.tick > event.tick) return;
    if (!this.historical && (event.event_kind === 'takeoff' || event.event_kind === 'landing')) {
      this.cues.set(role, {pose: event.event_kind, tick: event.tick, until: performance.now() + 100});
      clearTimeout(this.frame); this.frame = 0;
    } else if (['fell', 'respawn', 'underside_contact'].includes(event.event_kind)) {
      this.cues.delete(role);
    }
    // A same-tick state already reflects the entire tick; some events describe
    // an earlier moment within it. Keep the authoritative pose while showing cues.
    if (this.world.tick === event.tick) this.paint(true);
    else this.setWorld({...this.world, tick: event.tick, robots: {...this.world.robots, [role]: robot}});
  }

  say(role, value, seq) {
    if (ROLES.includes(role) && typeof value === 'string' && value.trim()) {
      this.speech.set(role, {text: value, seq});
    }
  }

  releaseSpeech() {
    const start = this.speechTime();
    let changed = false;
    for (const role of ROLES) {
      const actor = this.actors[role];
      const speech = this.speech.get(role);
      if (actor.speech?.seq === speech?.seq) continue;
      changed = true;
      actor.speech = speech && {...speech, start, duration: readingDuration(speech.text)};
      actor.message.textContent = speech?.text ?? '';
      actor.message.scrollTop = 0;
      actor.message.hidden = !speech;
      actor.bubble.classList.toggle('speaking', Boolean(speech));
    }
    this.paint(true);
    if (changed) this.updateSpeechScroll();
  }

  speechTime() {
    return (this.speechPausedAt ?? performance.now()) - this.speechPausedTotal;
  }

  setSpeechPaused(paused) {
    if (paused) this.speechPausedAt ??= performance.now();
    else if (this.speechPausedAt !== null) {
      this.speechPausedTotal += performance.now() - this.speechPausedAt;
      this.speechPausedAt = null;
    }
    this.pauseButton.textContent = paused ? 'Resume scrolling' : 'Pause scrolling';
    this.updateSpeechScroll();
  }

  updateSpeechScroll() {
    clearTimeout(this.speechTimer);
    this.speechTimer = 0;
    const now = this.speechTime();
    let advancing = false;
    for (const {speech, message} of Object.values(this.actors)) {
      if (speech && advanceMessage(message, Math.max(0, now - speech.start), speech.duration)) advancing = true;
    }
    if (advancing && this.speechPausedAt === null) {
      this.speechTimer = setTimeout(() => this.updateSpeechScroll(), 100);
    }
  }

  setConnected(value) {
    this.connected = value;
    if (!value) { clearTimeout(this.frame); this.frame = 0; }
    this.paint(true);
  }

  camera() {
    const width = this.stage.clientWidth, height = this.stage.clientHeight;
    if (!width || !height) {
      this.projectedFrame = null;
      return null;
    }
    if (this.usesManualPan()) {
      this.projectedFrame = null;
      const tile = width / 13.9;
      return this.projection(width, height, {tile, originX: width / 2 - 6 * tile, originY: height * .775});
    }

    const overviewTile = Math.min(width / (ROOM.right - ROOM.left), height / (ROOM.top - ROOM.bottom));
    const overview = cameraFrame(width, height, overviewTile, 6, (ROOM.bottom + ROOM.top) / 2);
    const previous = this.projectedFrame;
    const resized = previous?.width !== width || previous?.height !== height;
    if (resized) this.followCenter = null;
    const robot = this.world?.robots[this.followRole];
    let target = overview, start = previous;
    if (robot) {
      const tile = Math.max(overviewTile, Math.min(width / (width < height ? 5 : 6.5), height / 3.5));
      const x = robot.x / 256, y = robot.y / 256;
      const headCenter = y + .42;
      const horizontal = width / tile * .12, vertical = height / tile * .18;
      const cx = clamp(this.followCenter?.x ?? x, x - horizontal, x + horizontal);
      const cy = clamp(this.followCenter?.y ?? headCenter, headCenter - vertical, headCenter + vertical);
      this.followCenter = {
        x: cameraCenter(cx, width / tile, ROOM.left, ROOM.right),
        y: cameraCenter(cy, height / tile, ROOM.bottom, ROOM.top),
      };
      target = cameraFrame(width, height, tile, this.followCenter.x, this.followCenter.y);
      // Reveal a distant target or respawn before easing back into close framing.
      if (previous && !resized && !containsRobot(previous, width, height, x, y)) start = overview;
    }

    const now = performance.now();
    let frame = target;
    if (start && !resized && !this.reduced.matches && !document.hidden) {
      const weight = 1 - Math.exp(-clamp(now - previous.time, 0, 40) / 115);
      const blend = key => start[key] + (target[key] - start[key]) * weight;
      const next = {tile: blend('tile'), originX: blend('originX'), originY: blend('originY')};
      const remaining = Math.max(Math.abs(next.originX - target.originX), Math.abs(next.originY - target.originY),
        14 * Math.abs(next.tile - target.tile));
      if (remaining > .5) {
        frame = next;
        if (!this.cameraAnimation) {
          this.cameraAnimation = requestAnimationFrame(() => {
            this.cameraAnimation = 0;
            this.paint(true);
          });
        }
      }
    }
    this.projectedFrame = {...frame, width, height, time: now};
    return this.projection(width, height, frame);
  }

  projection(width, height, {tile, originX, originY}) {
    return {
      width, height, tile,
      x: x => originX + x / 256 * tile,
      y: y => originY - y / 256 * tile,
    };
  }

  drawScenery(view) {
    const ctx = this.context;
    const pixelRatio = Math.min(devicePixelRatio || 1, 2);
    const w = Math.round(view.width * pixelRatio), h = Math.round(view.height * pixelRatio);
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.clearRect(0, 0, view.width, view.height);
    const {tile, x, y} = view;
    const high = this.baseline ? 0 : 128;
    const img = (name, left, top, width, height, fallback) => {
      const image = this.assets.get(name);
      if (image) ctx.drawImage(image, ...STATIC_CROPS[name], left, top, width, height);
      else { ctx.fillStyle = fallback; ctx.fillRect(left, top, width, height); }
    };
    const bank = (first, last, elevation) => {
      const top = y(elevation);
      // The rock face continues below the deck. Its vertical edge is also the collision face.
      const left = x((first - .5) * 256), right = x((last + .5) * 256);
      const depth = ctx.createLinearGradient(0, top, 0, view.height);
      depth.addColorStop(0, '#ba9269'); depth.addColorStop(.6, '#e1bc94'); depth.addColorStop(1, '#e5c7a7');
      ctx.fillStyle = depth;
      ctx.fillRect(left, top + tile * .17, right - left, view.height - top);
      ctx.fillStyle = '#aa8768';
      ctx.fillRect(first === 0 ? right - 2 : left, top + tile * .2, 2, view.height - top);
      // The graphic begins at the exact collider top and ends on its two faces.
      for (let i = first; i <= last; i += 2) {
        const count = Math.min(2, last - i + 1);
        img('floor', x((i - .5) * 256), top, count * tile, .36 * tile, '#ab895a');
      }
    };
    bank(0, 4, 0);
    bank(8, 12, high);
    const world = this.world;
    if (world) {
      if (world.bridge_powered) img('bridge', x(1152), y(0), tile * 3, tile * .25, '#99805b');
      const prop = (key, column, elevation, width, height, color) => {
        img(key, x(column * 256) - width * tile / 2, y(elevation) - height * tile, width * tile, height * tile, color);
      };
      prop('motor-console', 4, 0, .53, .77, '#a46431');
      if (!world.shard_collected) prop('memory-shard', 9, high + 45, .34, .54, '#ba7014');
      if (!world.cell_collected) prop('energy-cell', 10, high + 30, .31, .52, '#427780');
      prop(world.exit_unlocked ? 'exit-open' : 'exit-closed', 12, high, .86, 1.07, '#80745d');
    }
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '600 ' + Math.max(10, Math.min(13, tile * .19)) + 'px Consolas, monospace';
    ctx.fillStyle = '#493c28';
    for (let col = 0; col <= 12; col++) ctx.fillText(String(col), x(col * 256), y(col > 7 ? high : 0) + tile * .37 + 9);
  }

  sprite(role, robot, view, now) {
    const actor = this.actors[role];
    const footX = view.x(robot.x), footY = view.y(robot.y);
    // The normalized art's nominal 216 visible pixels cover the 192-unit standing height.
    const size = view.tile * (192 / 256) * (256 / 216);
    let pose = Object.hasOwn(JUMP_FRAME, robot.pose) || robot.pose === 'walk' ? robot.pose : 'idle';
    const cue = this.cues.get(role);
    if (cue && !this.historical && now < cue.until && this.world.tick - cue.tick <= 8 &&
        !(cue.pose === 'landing' && ['takeoff', 'ascent', 'descent'].includes(pose)) &&
        !(cue.pose === 'takeoff' && ['landing', 'descent'].includes(pose))) pose = cue.pose;
    const action = Object.hasOwn(JUMP_FRAME, pose) ? 'jump' : pose;
    const slug = role.toLowerCase();
    const selected = this.assets.get(slug + '-' + action);
    const atlas = selected || this.assets.get(slug + '-idle');
    actor.mark.hidden = false;
    actor.mark.style.left = footX + 'px'; actor.mark.style.top = footY + 'px';
    Object.assign(actor.mark.dataset, {x: robot.x, y: robot.y, pose, authoritativePose: robot.pose, facing: robot.facing});
    const facing = robot.facing < 0 ? -1 : 1;
    const art = actor.art.style;
    art.width = size + 'px'; art.height = size + 'px';
    art.left = -size / 2 + 'px'; art.top = -size * 239 / 256 + 'px';
    art.transform = 'scaleX(' + facing + ')';
    if (atlas) {
      const key = selected ? action : 'idle';
      let frame = selected && action === 'jump' ? JUMP_FRAME[pose] : 0;
      if (!this.reduced.matches && key !== 'jump') {
        frame = key === 'walk' ? Math.floor(this.world.tick * 8 / 60) % 6 : Math.floor(now / 500) % 4;
      }
      art.backgroundImage = 'url("' + atlas.src + '")';
      art.backgroundSize = size * FRAME_COUNT[key] + 'px ' + size + 'px';
      art.backgroundPosition = -frame * size + 'px 0';
    } else {
      const source = this.assets.get(slug);
      art.backgroundImage = source ? 'url("' + source.src + '")' : 'none';
      if (source) {
        const [px, py, visible] = STATIC_FEET[role], scale = size * 216 / 256 / visible;
        art.backgroundSize = source.naturalWidth * scale + 'px ' + source.naturalHeight * scale + 'px';
        art.backgroundPosition = (size / 2 - px * scale) + 'px ' + (size * 239 / 256 - py * scale) + 'px';
      }
    }
    const top = footY - size * 239 / 256;
    return {role, x: footX, y: footY - size * .87,
      bounds: {left: footX - size / 2, right: footX + size / 2, top, bottom: top + size}};
  }

  placeBubbles(worldHeads, height) {
    const view = {width: this.scroll.clientWidth, height};
    const pan = this.scroll.scrollLeft;
    const heads = worldHeads.map(head => {
      const x = head.x - pan;
      const side = x < 0 ? 'left' : x > view.width ? 'right' :
        head.y < 0 ? 'above' : head.y > height ? 'below' : '';
      const actor = this.actors[head.role];
      actor.bubble.hidden = Boolean(side && !actor.speech);
      actor.leader.hidden = true;
      if (side) actor.bubble.dataset.offscreen = side;
      else delete actor.bubble.dataset.offscreen;
      return {...head, x, side, actor};
    });

    // Keep placement priority in role order as speaking robots cross on screen.
    const speakers = heads.filter(head => head.actor.speech);
    const subject = heads.find(head => head.role === this.followRole && !head.side)?.bounds;
    const reserved = subject ? [{...subject, left: subject.left - pan, right: subject.right - pan}] : [];
    const measure = ({actor: {bubble}}) => ({width: bubble.offsetWidth, height: bubble.offsetHeight});
    const messageIds = ROLES.map(role => this.actors[role].speech?.seq);
    const fitKey = [view.width, height, this.stageShell.dataset.speechSize, ...messageIds].join('/');
    if (fitKey !== this.bubbleFitKey) {
      // Re-evaluate on text/size changes, not on world frames. Toggling the clip
      // while a robot moves can clamp away the currently displayed last line.
      this.bubbleFitKey = fitKey;
      this.bubbleLayer.removeAttribute('data-compact');
      const gutter = BUBBLE_INSET * 2 + BUBBLE_GAP * (speakers.length - 1);
      const stackHeight = speakers.reduce((sum, head) => sum + measure(head).height, gutter);
      if (stackHeight > height) this.bubbleLayer.setAttribute('data-compact', '');
    }
    const boxes = [];
    if (!this.bubbleLayer.hasAttribute('data-compact')) {
      for (const head of speakers) {
        const size = measure(head);
        const box = bubbleBox(head, size.width, size.height, view, [...reserved, ...boxes]);
        if (!box) break;
        boxes.push(box);
      }
    }

    // Stack crowded bubbles from the top edge to leave the play area visible.
    if (boxes.length !== speakers.length) {
      boxes.length = 0;
      let top = BUBBLE_INSET;
      for (const head of speakers) {
        const size = measure(head);
        const left = clamp(head.x - size.width / 2, BUBBLE_INSET, view.width - size.width - BUBBLE_INSET);
        const bottom = top + size.height;
        boxes.push({left, top, right: left + size.width, bottom});
        top = bottom + BUBBLE_GAP;
      }
    }

    speakers.forEach((head, index) => this.drawBubble(head, boxes[index]));
    const labels = heads.filter(head => !head.actor.speech && !head.side).sort((a, b) => a.x - b.x);
    for (const head of labels) {
      const size = measure(head);
      const box = bubbleBox(head, size.width, size.height, view, [...reserved, ...boxes]);
      if (box) { boxes.push(box); this.drawBubble(head, box); }
      else head.actor.bubble.hidden = true;
    }
    const layout = speakers.map(({actor}) => [actor.message.clientWidth, actor.message.clientHeight].join('/')).join(',');
    if (layout !== this.speechLayout) {
      this.speechLayout = layout;
      this.updateSpeechScroll();
    }
  }

  drawBubble(head, box) {
    const {bubble, leader} = head.actor;
    bubble.style.left = box.left + 'px';
    bubble.style.top = box.top + 'px';
    if (head.side) return;
    const fromX = clamp(head.x, box.left + 4, box.right - 4);
    const fromY = head.y < box.top ? box.top : box.bottom;
    const dx = head.x - fromX, dy = head.y - fromY;
    leader.hidden = false;
    leader.style.left = fromX + 'px';
    leader.style.top = fromY + 'px';
    leader.style.width = Math.hypot(dx, dy) + 'px';
    leader.style.transform = 'rotate(' + Math.atan2(dy, dx) + 'rad)';
  }

  paint(scenery = false) {
    if (this.batching) return;
    const view = this.camera();
    if (!view) {
      // Switching to a sensor feed removes the stage from layout. Force speech
      // to catch up when the spectator returns to a same-sized stage.
      this.speechLayout = null;
      return;
    }
    scenery ||= !this.usesManualPan();
    if (scenery) this.drawScenery(view);
    if (!this.world) return;
    const now = this.connected ? performance.now() : this.lastPaint;
    this.lastPaint = now;
    const heads = ROLES.map(role => this.sprite(role, this.world.robots[role], view, now));
    if (scenery) this.placeBubbles(heads, view.height);
    if (this.connected && !this.frame && !document.hidden && !this.historical && (!this.reduced.matches || this.cues.size)) {
      // World updates already paint walking and motion. Wake only at an idle-frame
      // change or the end of a short, recorded contact cue while the room is still.
      const next = Math.min(500 - now % 500, ...[...this.cues.values()].map(cue => cue.until - now));
      this.frame = setTimeout(() => {
        this.frame = 0;
        for (const [role, cue] of this.cues) if (performance.now() >= cue.until) this.cues.delete(role);
        this.paint();
      }, Math.max(16, next));
    }
  }
}
