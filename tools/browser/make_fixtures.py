"""Generate disposable, explicit offline browser fixtures with the real driver."""
import asyncio
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'site'))
from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import MatchExecutionError, run_match
from parallax_relay.protocol import ROLES
from parallax_relay.recording import Recorder
from run_records import read_run

ATTACK = '</script><img src="https://invalid.example/probe" onerror="window.modelExecuted=true"><script>window.modelExecuted=true</script>'


def viewer(out, data):
    """Render the current viewer against supplied native records, including v2."""
    payload = {key: data[key] for key in ('manifest', 'result', 'calls', 'phases', 'final_state')}
    payload['records'] = data['replay']
    encoded = json.dumps(payload, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ROOT / 'parallax_relay/replay_template.html').read_text(encoding='utf-8')
    (out / 'index.html').write_text(template.replace('__REPLAY_DATA__', encoded), encoding='utf-8')


async def main(destination):
    destination.mkdir(parents=True)
    inventory = {}
    for name, settings in [('win', {}), ('turn-limit', {'max_turns': 1}),
                           ('later-partial', {'max_calls': 19}),
                           ('zero-turn-partial', {'max_calls': 10}),
                           ('zero-call', {'max_calls': 1}),
                           ('local-error', {}), ('cancelled', {})]:
        out = destination / name
        recorder = Recorder(out, {'mode': 'mock'})
        agents = {role: ScriptedAgent(role) for role in ROLES}
        if name == 'cancelled':
            started = asyncio.Event()
            class Slow(ScriptedAgent):
                async def respond(self, request):
                    started.set()
                    await asyncio.Event().wait()
            task = asyncio.create_task(run_match({r: Slow(r) for r in ROLES}, recorder=recorder))
            await started.wait()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            try:
                if name == 'local-error':
                    with patch.object(recorder, 'phase', side_effect=OSError('synthetic browser fixture write failure')):
                        await run_match(agents, recorder=recorder)
                else:
                    await run_match(agents, MatchSettings(**settings), recorder=recorder)
            except MatchExecutionError:
                if name != 'local-error':
                    raise
        data = read_run(out)
        (out / 'native.json').write_text(json.dumps(data), encoding='utf-8')
        inventory[name] = {'turns': data['result']['turns'], 'calls': len(data['calls']),
                           'phases': len(data['phases']), 'stop_reason': data['result']['stop_reason']}
    # Retain the committed historical schema, rather than fabricating v2 by relabeling v3.
    out = destination / 'legacy-v2'
    shutil.copytree(ROOT / 'example_run', out)
    data = read_run(out)
    assert data['manifest']['schema_version'] == 2
    viewer(out, data)
    (out / 'native.json').write_text(json.dumps(data), encoding='utf-8')
    inventory['legacy-v2'] = {'schema_version': 2, 'turns': data['result']['turns'], 'calls': len(data['calls'])}
    for name in ('missing-replay', 'missing-middle-replay'):
        out = destination / name
        shutil.copytree(destination / 'legacy-v2', out)
        data = read_run(out)
        data['replay'] = [] if name == 'missing-replay' else [row for row in data['replay'] if row['turn'] != 4]
        (out / 'replay.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in data['replay']), encoding='utf-8')
        viewer(out, data)
        (out / 'native.json').write_text(json.dumps(data), encoding='utf-8')
    for name in ('malicious', 'malicious-import', 'missing-images'):
        out = destination / name
        shutil.copytree(destination / 'later-partial', out)
        data = read_run(out)
        if name.startswith('malicious'):
            if name == 'malicious':
                data['manifest']['room'] = ATTACK
            data['phases'][-1]['messages'][0]['text'] = ATTACK
            data['replay'][0]['communications'][0]['text'] = ATTACK
            data['replay'][0]['private_notes']['SPECTRA'] = ATTACK
            data['calls'][-1]['error'] = ATTACK
        else:
            data['images'] = {}
            for image in out.glob('*.png'):
                image.unlink()
        viewer(out, data)
        (out / 'native.json').write_text(json.dumps(data), encoding='utf-8')
    (destination / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    print(json.dumps(inventory))


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1])))
