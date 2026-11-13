"""Incremental spectator logs and an offline, text-safe replay viewer."""
from __future__ import annotations

import json
from pathlib import Path
from .render import render_png


def _safe_metadata(value):
    if isinstance(value, dict):
        secret_keys = {'api_key', 'authorization', 'x-api-key', 'x-goog-api-key', 'access_token', 'password'}
        return {k: '[REDACTED]' if str(k).lower() in secret_keys else _safe_metadata(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_metadata(v) for v in value]
    return value


class RecordingFinalizationError(RuntimeError):
    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__('Recording finalization failed')


class Recorder:
    def __init__(self, out: Path, manifest: dict):
        self.out = out
        # An existing directory is never silently overwritten, even if empty.
        out.mkdir(parents=True, exist_ok=False)
        self.viewer_ready = False
        self.manifest = _safe_metadata(manifest)
        self.manifest['privacy'] = 'Privileged spectator files: all goals, views and notes. Never send to a player.'
        self._json('manifest.json', self.manifest)
        for filename in ('calls.jsonl', 'phases.jsonl', 'replay.jsonl'):
            (out / filename).touch()

    def _json(self, filename: str, data) -> None:
        self._bytes(filename, json.dumps(data, indent=2, ensure_ascii=True).encode('utf-8'))

    def _bytes(self, filename: str, data: bytes) -> None:
        target = self.out / filename
        temp = target.with_suffix(target.suffix + '.tmp')
        temp.write_bytes(data)
        temp.replace(target)

    def _append(self, filename: str, data: dict) -> None:
        with (self.out / filename).open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(data, ensure_ascii=True) + '\n')
            handle.flush()

    def begin_turn(self, world, observations: dict) -> None:
        for role, observation in observations.items():
            (self.out / f'turn_{world.turn:02d}_{role.lower()}.png').write_bytes(observation.image_png)
        (self.out / f'turn_{world.turn:02d}_spectator.png').write_bytes(render_png(world, 'SPECTATOR'))

    def call(self, record: dict) -> None:
        self._append('calls.jsonl', record)

    def phase(self, record: dict) -> None:
        self._append('phases.jsonl', record)

    def turn(self, record: dict) -> None:
        self._append('replay.jsonl', record)

    def _viewer(self, result) -> bytes:
        template = Path(__file__).with_name('replay_template.html').read_text(encoding='utf-8')
        data = json.dumps({'manifest': self.manifest, 'result': result.summary(),
                           'records': result.records, 'calls': result.calls}, ensure_ascii=True)
        data = data.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return template.replace('__REPLAY_DATA__', data).encode('utf-8')

    def finish(self, result) -> None:
        self.viewer_ready = False
        failures = []
        def snapshot(rows):
            return ''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in rows).encode('utf-8')
        artifacts = [
            ('calls.jsonl', lambda: self._bytes('calls.jsonl', snapshot(result.calls))),
            ('phases.jsonl', lambda: self._bytes('phases.jsonl', snapshot(result.phases))),
            ('replay.jsonl', lambda: self._bytes('replay.jsonl', snapshot(result.records))),
            ('result.json', lambda: self._json('result.json', result.summary())),
            ('final_state.json', lambda: self._json('final_state.json', result.world.snapshot())),
            ('final_spectator.png', lambda: self._bytes('final_spectator.png', render_png(result.world, 'SPECTATOR'))),
            ('index.html', lambda: self._bytes('index.html', self._viewer(result))),
        ]
        for operation, write in artifacts:
            try:
                write()
                if operation == 'index.html':
                    self.viewer_ready = True
            except Exception as error:
                failures.append((operation, error))
        if failures:
            raise RecordingFinalizationError(failures) from None
