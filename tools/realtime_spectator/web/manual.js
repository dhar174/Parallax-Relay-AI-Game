import {ROLES} from './scene.js';

const KINDS = ['WAIT', 'RUN', 'JUMP', 'VENT', 'REROUTE', 'COLLECT'];

function element(tag, parent, text) {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  parent.append(el);
  return el;
}

function field(row, title, key, options) {
  const label = element('label', row, title);
  const input = element(options ? 'select' : 'input', label);
  input.setAttribute('aria-label', title);
  input.dataset[key] = '';
  if (options) {
    for (const [value, text] of options) input.add(new Option(text, value));
  } else {
    input.type = 'number';
    input.step = '1';
    input.inputMode = 'numeric';
  }
  return input;
}

function button(parent, label, key) {
  const el = element('button', parent, label);
  el.type = 'button';
  el.dataset[key] = '';
  return el;
}

function integer(input) {
  return input.value !== '' && Number.isSafeInteger(input.valueAsNumber) ? input.valueAsNumber : null;
}

export class Manual {
  constructor(post) {
    this.post = post;
    this.limits = {action_points: 8, window_ticks: 120, max_commands: 4};
    this.roles = new Map();
    this.online = false;
    for (const role of ROLES) {
      const box = element('div', document.querySelector('#editors'));
      box.className = 'editor';
      box.dataset.editor = role;
      const title = element('h3', box, role);
      title.id = 'editor-' + role;
      box.setAttribute('role', 'group');
      box.setAttribute('aria-labelledby', title.id);
      const list = element('div', box);
      const points = element('p', box);
      points.className = 'points'; points.dataset.points = '';
      const buttons = element('div', box);
      buttons.className = 'editor-tools';
      const add = button(buttons, 'Add command', 'add');
      const submit = button(buttons, 'Seal ' + role + ' plan', 'submit');
      const feedback = element('p', box);
      feedback.className = 'feedback'; feedback.dataset.feedback = '';
      feedback.setAttribute('role', 'status');
      const editor = {role, list, points, add, submit, feedback, slot: null, sealed: false, sending: false};
      this.roles.set(role, editor);
      this.addRow(editor);
      add.addEventListener('click', () => this.addRow(editor, true));
      submit.addEventListener('click', () => this.submit(editor));
    }
  }

  configure(mode, settings) {
    document.querySelector('#manual').hidden = mode !== 'manual';
    for (const key of Object.keys(this.limits)) {
      if (Number.isSafeInteger(settings[key]) && settings[key] > 0) this.limits[key] = settings[key];
    }
    document.querySelector('#limits').textContent = this.limits.action_points + ' AP per robot · ' + this.limits.window_ticks + ' ticks';
    this.refresh();
  }

  addRow(editor, focus = false) {
    if (editor.list.children.length >= this.limits.max_commands) return;
    const row = element('div', editor.list);
    row.className = 'command';
    const kind = field(row, 'Command', 'kind', KINDS.map(k => [k, k]));
    const direction = field(row, 'Direction', 'direction', [['1', 'Right'], ['-1', 'Left']]);
    const ticks = field(row, 'Duration (ticks)', 'ticks');
    const jump = field(row, 'Jump at tick', 'jump');
    jump.placeholder = 'None'; jump.min = '0';
    const remove = button(row, 'Remove command', 'remove');
    remove.className = 'remove';
    const fields = () => {
      const run = kind.value === 'RUN', wait = kind.value === 'WAIT';
      direction.parentElement.hidden = jump.parentElement.hidden = !run;
      ticks.parentElement.hidden = !run && !wait;
      ticks.value = run ? '15' : wait ? '1' : '';
      ticks.min = '1'; ticks.max = run ? '90' : '120';
      jump.value = '';
      this.update(editor);
    };
    kind.addEventListener('change', fields);
    row.addEventListener('input', () => this.update(editor));
    remove.addEventListener('click', () => {
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      this.update(editor);
      (next?.querySelector('[data-kind]') || editor.add).focus();
    });
    fields();
    if (focus) kind.focus();
  }

  read(editor) {
    const actions = [];
    let cost = 0, duration = 0, error = '';
    const rows = [...editor.list.children];
    for (const [i, row] of rows.entries()) {
      const kind = row.querySelector('[data-kind]').value, run = kind === 'RUN', wait = kind === 'WAIT';
      const ticksInput = row.querySelector('[data-ticks]'), jumpInput = row.querySelector('[data-jump]');
      const ticks = run || wait ? integer(ticksInput) : null;
      const direction = run ? Number(row.querySelector('[data-direction]').value) : null;
      const jump = run ? integer(jumpInput) : null;
      const validTicks = !(run || wait) || (ticks !== null && ticks >= 1 && ticks <= (run ? 90 : 120));
      const validJump = !run || (!jumpInput.validity.badInput && (jumpInput.value === '' || jump !== null && jump >= 0 && jump < ticks));
      ticksInput.setAttribute('aria-invalid', String(!validTicks));
      jumpInput.setAttribute('aria-invalid', String(!validJump));
      if (run && ticks !== null) jumpInput.max = String(ticks - 1);
      else jumpInput.removeAttribute('max');
      if (!validTicks && !error) error = 'Command ' + (i + 1) + ': use a whole duration from 1 to ' + (run ? 90 : 120) + ' ticks.';
      if (!validJump && !error) error = 'Command ' + (i + 1) + ': use a jump offset from 0 to duration minus one, or leave it empty.';
      if (validTicks) duration += ticks ?? 1;
      if (run && validTicks) cost += Math.ceil(ticks / 15) + (jump === null ? 0 : 2);
      else if (!wait && !run) cost += 2;
      actions.push({kind, direction, ticks, jump_at: jump});
    }
    if (!error && (actions.length === 0 || actions.length > this.limits.max_commands)) error = 'Use 1–' + this.limits.max_commands + ' commands.';
    if (!error && duration > this.limits.window_ticks) error = 'Sequence exceeds the ' + this.limits.window_ticks + '-tick window.';
    if (!error && cost > this.limits.action_points) error = 'Sequence exceeds the ' + this.limits.action_points + '-point budget.';
    return {actions, cost, duration, error};
  }

  report(editor, message, error = false) {
    editor.feedback.textContent = message;
    editor.feedback.dataset.error = String(error);
  }

  update(editor) {
    const {cost, duration, error} = this.read(editor);
    editor.points.textContent = (this.limits.action_points - cost) + ' AP remaining · ' + duration + '/' + this.limits.window_ticks + ' ticks' + (error ? ' · ' + error : '');
    editor.points.classList.toggle('invalid', Boolean(error));
    const locked = !editor.slot || editor.sealed || editor.sending;
    for (const field of editor.list.querySelectorAll('input,select,button')) field.disabled = locked;
    for (const remove of editor.list.querySelectorAll('[data-remove]')) remove.disabled = locked || editor.list.children.length === 1;
    editor.add.disabled = locked || editor.list.children.length >= this.limits.max_commands;
    editor.submit.disabled = !this.online || !editor.slot || locked;
  }

  refresh() { for (const editor of this.roles.values()) this.update(editor); }

  close(window, reason, reset = false) {
    for (const editor of this.roles.values()) {
      if (editor.slot && !reset) this.report(editor, 'Window ' + editor.slot.window + ' closed. ' + reason, !editor.sealed);
      if (reset) this.report(editor, '');
      editor.slot = null; editor.sealed = false; editor.sending = false;
      this.update(editor);
    }
  }

  request(event) {
    const editor = this.roles.get(event.role);
    if (!editor || !Number.isSafeInteger(event.window) || typeof event.request_id !== 'string') return;
    if (editor.slot?.request_id === event.request_id) return;
    editor.slot = {window: event.window, request_id: event.request_id};
    editor.sealed = false; editor.sending = false;
    this.report(editor, 'Window ' + event.window + ' is accepting a plan.');
    this.update(editor);
  }

  ready(role, disposition, reason) {
    const editor = this.roles.get(role);
    if (!editor?.slot) return;
    editor.sealed = true;
    this.report(editor, disposition === 'ready' || disposition === 'accepted' || disposition === 'ok' ?
      'Plan sealed for window ' + editor.slot.window + '.' : 'Slot closed · ' + (reason || disposition) + '.', !['ready', 'accepted', 'ok'].includes(disposition));
    this.update(editor);
  }

  async submit(editor) {
    const slot = editor.slot;
    if (!slot || editor.sealed || editor.sending) return;
    const {actions, error} = this.read(editor);
    if (error) { this.report(editor, error, true); return; }
    editor.sending = true;
    this.report(editor, 'Submitting…');
    this.update(editor);
    try {
      const reply = await this.post('/api/plan', {...slot, role: editor.role, actions});
      if (editor.slot !== slot || editor.sealed) return;
      if (!reply.ok) throw new Error(reply.error || 'The host rejected this plan.');
      editor.sealed = true;
      this.report(editor, 'Plan sealed for window ' + slot.window + '.');
    } catch (error) {
      if (editor.slot === slot && !editor.sealed) this.report(editor, error.message, true);
    } finally {
      if (editor.slot === slot) { editor.sending = false; this.update(editor); }
    }
  }
}
