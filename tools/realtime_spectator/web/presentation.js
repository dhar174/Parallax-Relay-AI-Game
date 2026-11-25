export class StagePresentation {
  constructor(scene) {
    this.scene = scene;
    this.shell = scene.stageShell;
    this.button = document.getElementById('stage-fullscreen');
    this.note = document.getElementById('stage-mode-note');
    this.reader = document.getElementById('speech-reader');
    this.mode = '';
    this.pageScroll = null;
    this.inert = [];
    this.button.addEventListener('click', () => this.toggle());
    document.addEventListener('fullscreenchange', () => {
      if (document.fullscreenElement === this.shell) this.enter('native');
      else if (this.mode === 'native') this.leave();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !event.defaultPrevented && this.mode === 'game-only' && !this.reader.open) {
        event.preventDefault();
        this.leave();
      }
    });
  }

  setNote(message) {
    this.note.textContent = message;
    this.note.hidden = !message;
  }

  async toggle() {
    if (this.mode === 'game-only') { this.leave(); return; }
    if (this.mode === 'native') {
      try { await document.exitFullscreen(); }
      catch { if (document.fullscreenElement === this.shell) this.setNote('Use your browser controls to exit fullscreen.'); }
      return;
    }
    if (this.button.disabled) return;
    this.pageScroll = {left: window.scrollX, top: window.scrollY};
    if (!document.fullscreenEnabled || typeof this.shell.requestFullscreen !== 'function') {
      this.enter('game-only');
      return;
    }
    this.button.disabled = true;
    try {
      await this.shell.requestFullscreen();
      if (document.fullscreenElement === this.shell) this.enter('native');
    } catch {
      this.enter('game-only');
    } finally {
      this.button.disabled = false;
      this.button.focus({preventScroll: true});
    }
  }

  enter(mode) {
    if (this.mode === mode) return;
    this.pageScroll ??= {left: window.scrollX, top: window.scrollY};
    if (!this.mode) {
      // Walk out from the stage without making any of its ancestors inert.
      for (let node = this.shell; node !== document.body; node = node.parentElement) {
        for (const sibling of node.parentElement.children) {
          if (sibling !== node && !sibling.inert) {
            sibling.inert = true;
            this.inert.push(sibling);
          }
        }
      }
      document.body.classList.add('stage-presenting');
    }
    this.mode = mode;
    this.setNote(mode === 'game-only' ? 'Game-only view' : '');
    this.button.textContent = 'Exit to dashboard';
    this.scene.setPresentation(mode);
    this.button.focus({preventScroll: true});
  }

  leave() {
    if (this.reader.open) this.reader.close();
    this.mode = '';
    this.setNote('');
    this.button.textContent = 'Fullscreen';
    this.scene.setPresentation('');
    for (const sibling of this.inert) sibling.inert = false;
    this.inert.length = 0;
    document.body.classList.remove('stage-presenting');
    if (this.pageScroll) window.scrollTo({...this.pageScroll, behavior: 'instant'});
    this.pageScroll = null;
    this.button.focus({preventScroll: true});
  }
}
