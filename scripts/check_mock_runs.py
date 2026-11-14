"""Check both real scripted CLIs without retaining spectator artifacts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    blocked = {provider + '_' + suffix
               for provider in ('OPENAI', 'ANTHROPIC', 'GEMINI')
               for suffix in ('API_KEY', 'MODEL')}
    env = {key: value for key, value in os.environ.items() if key.upper() not in blocked}
    mode = 'setup'
    try:
        with tempfile.TemporaryDirectory(prefix='parallax-mock-check-') as directory:
            for mode, flags, calls in [('normal', [], 63), ('fast', ['--fast'], 42)]:
                out = Path(directory) / mode
                proc = subprocess.run(
                    [sys.executable, '-m', 'parallax_relay.play', '--mock', '--quiet',
                     '--out', str(out), *flags],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
                if proc.returncode != 0:
                    raise ValueError(f'exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}')
                result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
                expected = {'win': True, 'loss': False, 'completed': True,
                            'stop_reason': 'victory', 'turns': 7, 'energy': 5,
                            'scores': dict.fromkeys(('SPECTRA', 'PYRA', 'FLUX'), 100)}
                if not isinstance(result, dict):
                    raise ValueError('result.json must contain an object')
                for key, value in expected.items():
                    if result.get(key) != value:
                        raise ValueError(f'{key}: expected {value!r}, got {result.get(key)!r}')
                budget = result.get('budget')
                actual_calls = budget.get('calls_started') if isinstance(budget, dict) else None
                if actual_calls != calls:
                    raise ValueError(f'calls_started: expected {calls}, got {actual_calls!r}')
                print(f'{mode}: victory, 7 turns, {calls} calls, 5 energy, all scores 100')
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'{mode} mock check failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
