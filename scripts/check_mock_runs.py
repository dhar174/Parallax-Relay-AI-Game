"""Check both real scripted CLIs without retaining spectator artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def _expect(actual, expected, field):
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f'{field}: expected {expected!r}, got {actual!r}')
    if isinstance(expected, dict):
        for key, value in expected.items():
            _expect(actual[key], value, field + '.' + key)


def _text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''


def main() -> int:
    blocked = {provider + '_' + suffix
               for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI')
               for suffix in ('API_KEY', 'MODEL')}
    blocked.update({'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONHOME', 'PYTHONINSPECT'})
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in blocked and 'PROXY' not in key.upper()
           and not key.upper().endswith('_BASE_URL')}
    # Standardize child stdio without masking native filesystem encoding in tests.
    env['PYTHONIOENCODING'] = 'utf-8'
    mode = 'setup'
    proc = None
    try:
        with tempfile.TemporaryDirectory(prefix='parallax-mock-check-') as directory:
            for mode, flags, calls in [('normal', [], 63), ('fast', ['--fast'], 42)]:
                out = Path(directory) / mode
                proc = None
                proc = subprocess.run(
                    [sys.executable, '-m', 'parallax_relay.play', '--mock', '--quiet',
                     '--out', str(out), *flags],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=120)
                if proc.returncode != 0:
                    raise ValueError(f'exit {proc.returncode}')
                if any(line.startswith(('Round ', 'MOCK scripted fixture;')) for line in proc.stdout.splitlines()):
                    raise ValueError('--quiet emitted banner or progress output')
                result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
                expected = {'win': True, 'loss': False, 'completed': True,
                            'stop_reason': 'victory', 'turns': 7, 'energy': 5,
                            'scores': dict.fromkeys(('SPECTRA', 'PYRA', 'FLUX'), 100)}
                if not isinstance(result, dict):
                    raise ValueError('result.json must contain an object')
                for key, value in expected.items():
                    _expect(result.get(key), value, key)
                budget = result.get('budget')
                actual_calls = budget.get('calls_started') if isinstance(budget, dict) else None
                _expect(actual_calls, calls, 'calls_started')
                for name in ('index.html', 'manifest.json', 'calls.jsonl'):
                    artifact = out / name
                    if not artifact.is_file() or artifact.stat().st_size == 0:
                        raise ValueError(f'Missing or empty artifact: {name}')
                print(f'{mode}: victory, 7 turns, {calls} calls, 5 energy, all scores 100')
            mode = 'cleanup'
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'{mode} mock check failed: {exc}', file=sys.stderr)
        source = exc if isinstance(exc, subprocess.TimeoutExpired) else proc
        if source is not None:
            print(f'stdout: {_text(source.stdout)}\nstderr: {_text(source.stderr)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
