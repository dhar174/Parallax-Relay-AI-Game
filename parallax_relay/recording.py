"""Incremental spectator logs and an offline, text-safe replay viewer."""
from __future__ import annotations

import json
from pathlib import Path
from .render import render_png
from .provenance import ProvenanceContext, RunProvenance


def _safe_metadata(value):
    if isinstance(value, dict):
        secret_keys = {'api_key', 'authorization', 'x-api-key', 'x-goog-api-key', 'access_token', 'password'}
        return {k: '[REDACTED]' if str(k).lower() in secret_keys else _safe_metadata(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(v) for v in value]
    return value


class RecordingFinalizationError(RuntimeError):
    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__('Recording finalization failed')


class Recorder:
    def __init__(self, out: Path, manifest: dict, *, context: ProvenanceContext | None = None):
        self.out = out
        # Capture source state before newly generated output can make it dirty.
        self._provenance = RunProvenance(context)
        self._match_attempted = False
        # An existing directory is never silently overwritten, even if empty.
        out.mkdir(parents=True, exist_ok=False)
        self.viewer_ready = False
        self.manifest = _safe_metadata(manifest)
        self.manifest['schema_version'] = 3
        self.manifest['provenance'] = self._provenance.snapshot()
        players = {role: {key: player[key] for key in ('provider', 'model')}
                   for role, player in self.manifest['provenance']['players'].items()}
        if context is not None:
            self.manifest.update(mode=context.mode, players=players)
        else:
            # Legacy spectator labels remain caller declarations; they do not
            # infer the execution identity of arbitrary in-process agents.
            self.manifest.setdefault('mode', 'programmatic')
            self.manifest.setdefault('players', players)
        self.manifest['privacy'] = 'Privileged spectator files: all goals, views and notes. Never send to a player.'
        self._json('manifest.json', self.manifest)
        for filename in ('calls.jsonl', 'phases.jsonl', 'replay.jsonl'):
            (out / filename).touch()

    @property
    def match_started(self):
        return self._match_attempted or self._provenance.bound

    def _claim_match(self):
        if self.match_started:
            raise ValueError('Recorder already bound to a match')
        self._match_attempted = True

    def begin_match(self, settings, rates, initial_snapshot):
        self._match_attempted = True
        self._provenance.begin(settings, rates, initial_snapshot)
        self.manifest['settings'] = settings.model_dump()
        self.manifest['room']=settings.room_id
        self.manifest['provenance'] = self._provenance.snapshot()
        self._json('manifest.json', self.manifest)

    def end_match(self, result):
        if self._provenance.bound:
            self._provenance.end(result)
        self.manifest['provenance'] = self._provenance.snapshot()

    def _json(self, filename: str, data) -> None:
        self._bytes(filename, json.dumps(data, indent=2, ensure_ascii=True).encode('utf-8'))

    def _bytes(self, filename: str, data: bytes) -> None:
        target = self.out / filename
        temp = target.with_suffix(target.suffix + '.tmp')
        temp.write_bytes(data)
        temp.replace(target)

    def _append(self, filename: str, data: dict) -> None:
        with (self.out / filename).open('a', encoding='utf-8', newline='\n') as handle:
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
                           'records': result.records, 'calls': result.calls,
                           'phases': result.phases, 'final_state': result.world.snapshot()},
                          ensure_ascii=True)
        data = data.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return template.replace('__REPLAY_DATA__', data).encode('utf-8')

    def finish(self, result) -> None:
        self.viewer_ready = False
        if not self.match_started:
            self._provenance.end(result)  # External result: no invented execution times.
        if self._provenance.snapshot()['lifecycle']['stage']=='external_result':
            # Describe the supplied world without claiming execution inputs/times.
            self.manifest['room']=result.world.room.id
            self.manifest['room_definition']=result.world.room.model_dump(mode='json')
        self._provenance.refresh(result)
        self.manifest['provenance'] = self._provenance.snapshot()
        failures = []
        def snapshot(rows):
            return ''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in rows).encode('utf-8')
        artifacts = [
            ('manifest.json', lambda: self._json('manifest.json', self.manifest)),
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
