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

function make(tag, className, parent) {
  const node = document.createElement(tag);
  node.className = className;
  parent.append(node);
  return node;
}

export class Scene {
  constructor() {
    this.stage = document.querySelector('#stage');
    this.canvas = document.querySelector('#scenery');
    this.context = this.canvas.getContext('2d');
    this.actors = {};
    this.assets = new Map();
    this.world = null;
    this.baseline = false;
    this.connected = false;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)');
    this.speech = new Map();
    this.positionText = new Map();
    this.cues = new Map();
    this.batching = false;
    this.frame = 0;
    this.lastPaint = 0;
    this.historical = false;
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
      const layer = document.querySelector('#bubbles');
      const leader = make('span', 'leader', layer);
      const bubble = make('div', 'bubble', layer);
      bubble.dataset.bubble = role;
      bubble.style.setProperty('--role-color', COLORS[role]);
      const speaker = make('b', 'bubble-speaker', bubble);
      speaker.textContent = role;
      const message = make('span', 'bubble-message', bubble);
      this.actors[role] = {mark, art, leader, bubble, message};
      mark.hidden = bubble.hidden = leader.hidden = true;
    }
    this.resize = new ResizeObserver(() => this.paint(true));
    this.resize.observe(this.stage);
    this.reduced.addEventListener('change', () => this.paint(true));
    const zoom = document.querySelector('#zoom');
    const scroll = document.querySelector('#stage-scroll');
    zoom.addEventListener('click', () => {
      const enlarged = scroll.classList.toggle('enlarged');
      zoom.setAttribute('aria-pressed', String(enlarged));
      zoom.textContent = enlarged ? 'Room overview' : 'Enlarge room';
      scroll.setAttribute('aria-label', enlarged ? 'Enlarged room. Use arrow keys to pan.' : 'Room overview');
      if (!enlarged) scroll.scrollLeft = 0;
      this.paint(true);
    });
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
    this.speech.clear();
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
    this.setWorld({...this.world, tick: event.tick, robots: {...this.world.robots, [role]: robot}});
  }

  say(role, value, window, phase) {
    if (ROLES.includes(role) && typeof value === 'string' && value.trim()) {
      this.speech.set(role, {text: value, window, phase});
    }
  }

  releaseSpeech() {
    for (const role of ROLES) {
      const actor = this.actors[role];
      const text = this.speech.get(role)?.text || '';
      const chars = Array.from(text);
      actor.message.textContent = chars.length > 90 ? chars.slice(0, 89).join('') + '…' : text;
      actor.message.hidden = !text;
      actor.bubble.classList.toggle('speaking', Boolean(text));
    }
    this.paint(true);
  }

  setConnected(value) {
    this.connected = value;
    if (!value) { clearTimeout(this.frame); this.frame = 0; }
    this.paint(true);
  }

  camera() {
    const width = this.stage.clientWidth, height = this.stage.clientHeight;
    if (!width || !height) return null;
    const tile = width / 13.9;
    return {
      width, height, tile, deck: height * .775,
      x: x => width / 2 + (x / 256 - 6) * tile,
      y: y => height * .775 - y / 256 * tile,
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
    return {role, x: footX, y: footY - size * .87};
  }

  placeBubbles(heads, view) {
    const placed = [];
    for (const head of [...heads].sort((a, b) => a.x - b.x)) {
      const {bubble, leader} = this.actors[head.role];
      bubble.hidden = false;
      const width = bubble.offsetWidth, height = bubble.offsetHeight;
      const natural = clamp(head.x - width / 2, 4, view.width - width - 4);
      const options = [natural, ...placed.flatMap(box => [box.left - width - 5, box.right + 5])];
      let best, bestCost = Infinity;
      for (let row = 0; row <= heads.length; row++) {
        const top = clamp(head.y - height - 8 - row * (height + 5), 3, view.height - height - 3);
        for (const delta of options) {
          const left = clamp(delta, 4, view.width - width - 4);
          const right = left + width, bottom = top + height;
          const overlaps = placed.some(b => left < b.right + 3 && right > b.left - 3 && top < b.bottom + 3 && bottom > b.top - 3);
          const cost = (overlaps ? 1e6 : 0) + Math.abs(left - natural) + row * 44;
          if (cost < bestCost) { bestCost = cost; best = {left, top, right, bottom}; }
        }
      }
      placed.push(best);
      bubble.style.left = best.left + 'px'; bubble.style.top = best.top + 'px';
      const fromX = clamp(head.x, best.left + 4, best.right - 4), fromY = best.bottom;
      const dx = head.x - fromX, dy = head.y - fromY;
      leader.hidden = false;
      leader.style.left = fromX + 'px'; leader.style.top = fromY + 'px';
      leader.style.width = Math.hypot(dx, dy) + 'px';
      leader.style.transform = 'rotate(' + Math.atan2(dy, dx) + 'rad)';
    }
  }

  paint(scenery = false) {
    if (this.batching) return;
    const view = this.camera();
    if (!view) return;
    if (scenery) this.drawScenery(view);
    if (!this.world) return;
    const now = this.connected ? performance.now() : this.lastPaint;
    this.lastPaint = now;
    const heads = ROLES.map(role => this.sprite(role, this.world.robots[role], view, now));
    if (scenery) this.placeBubbles(heads, view);
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
