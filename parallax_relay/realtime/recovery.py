"""A stopped supervisor's local receipt, derived only from its own durable journal."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from uuid import UUID

from ..money import amount, total
from ..protocol import ROLES, _unique_object
from .supervise import SupervisionResult

_RECOVERY_VERSION = 2  # Version that binds every row to the supervisor's run UUID.
_MAX_LINE = 4 * 1024 * 1024


def _owned_rows(path: Path, run_id: str):
    with path.open('rb') as stream:
        while line := stream.readline(_MAX_LINE + 1):
            if len(line) > _MAX_LINE or not line.endswith(b'\n'):
                raise ValueError('incomplete record')
            row = json.loads(line, object_pairs_hook=_unique_object)
            if (type(row) is not dict or type(row.get('version')) is not int
                    or row['version'] != _RECOVERY_VERSION or row.get('run_id') != run_id):
                raise ValueError('record identity mismatch')
            yield row


def _checkpoint(out: Path, run_id: str) -> dict:
    tick = state_hash = None
    finished = False
    status = 'journaled'
    try:
        for row in _owned_rows(out / 'simulation.jsonl', run_id):
            kind = row.get('type')
            if finished or type(row.get('tick')) is not int:
                raise ValueError('invalid simulation order')
            if kind == 'finish' and tick is not None and row['tick'] == tick:
                finished = True
                continue
            expected_tick = 0 if tick is None else tick + 1
            expected_kind = 'initial' if tick is None else 'tick'
            digest = row.get('state_hash')
            if (kind != expected_kind or row['tick'] != expected_tick
                    or type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise ValueError('invalid checkpoint')
            tick, state_hash = expected_tick, digest
    except (OSError, ValueError, RecursionError):
        status = 'partial'
    return {'status': status if tick is not None else 'unavailable', 'last_journaled_tick': tick,
            'state_sha256': state_hash, 'finish_marker_seen': finished}


def _summed(values):
    values = list(values)
    if any(value is None for value in values):
        return None
    return str(total(values))


def _recorded_price(data: dict, key: str):
    value = amount(data, key)
    if value is not None and not isinstance(data.get(key + '_decimal'), str):
        raise ValueError('missing exact price')
    return value


def _accounting(out: Path, run_id: str) -> dict:
    pending, settled = {}, {}
    undispatched = 0
    status = 'readable'
    try:
        for row in _owned_rows(out / 'private.jsonl', run_id):
            kind = row.get('kind')
            if kind not in ('attempt_started', 'attempt'):
                continue
            data = row.get('data')
            if type(data) is not dict or data.get('request_run_id') != run_id:
                raise ValueError('invalid attempt evidence')
            key = data.get('request_id')
            role, phase, window = data.get('role'), data.get('phase'), data.get('window')
            sample_tick, attempt = data.get('sample_tick'), data.get('attempt')
            if (type(key) is not str or not re.fullmatch('[0-9a-f]{32}', key) or role not in ROLES
                    or phase not in ('broadcast', 'negotiate', 'commit') or type(window) is not int or window < 1
                    or type(sample_tick) is not int or sample_tick < 0 or type(attempt) is not int or attempt < 1):
                raise ValueError('invalid attempt slot')
            slot = (role, phase, window, sample_tick, attempt, _recorded_price(data, 'reservation_quote_usd'))
            if kind == 'attempt_started':
                if key in pending or key in settled:
                    raise ValueError('duplicate attempt start')
                pending[key] = slot
                continue
            if pending.get(key) != slot:
                raise ValueError('unpaired settlement')
            charge = _recorded_price(data, 'settled_amount_usd')
            quote = slot[-1]
            basis = data.get('settlement_basis')
            if (basis not in ('complete_usage', 'retained_estimate', 'not_dispatched')
                    or (charge is None) != (quote is None) or (basis == 'retained_estimate' and charge != quote)):
                raise ValueError('invalid settlement')
            if basis == 'not_dispatched' or data.get('status') == 'not_dispatched':
                if charge not in (None, 0) or basis != 'not_dispatched' or data.get('status') != 'not_dispatched':
                    raise ValueError('invalid undispatched settlement')
                charge = 0
                undispatched += 1
            settled[key] = charge
            del pending[key]
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        status = 'partial'
    retained = [item[-1] for item in pending.values()]
    unmatched = [{'request_id': key, 'role': role, 'phase': phase, 'window': window,
                  'sample_tick': tick, 'attempt': attempt,
                  'reservation_quote_usd_decimal': str(quote) if quote is not None else None}
                 for key, (role, phase, window, tick, attempt, quote) in pending.items()]
    return {'status': status, 'starts_observed': len(settled) + len(pending),
            'settlements_observed': len(settled), 'confirmed_not_dispatched': undispatched,
            'possibly_dispatched_unsettled': unmatched,
            'settled_estimate_usd_decimal': _summed(settled.values()),
            'retained_unsettled_usd_decimal': _summed(retained),
            'local_estimated_total_usd_decimal': _summed([*settled.values(), *retained]) if status == 'readable' else None}


def interruption_receipt(out: Path, run_id: str, result: SupervisionResult) -> dict:
    """Read only complete records under the canonical UUID issued before launching this child."""
    if str(UUID(run_id)) != run_id or result.status not in ('interrupted', 'wall_timeout'):
        raise ValueError('invalid supervision receipt identity')
    data = {'version': 1, 'run_id': run_id, 'supervisor_stop_reason': result.status,
            'exit_code': result.exit_code, 'child_exit_code': result.child_exit_code,
            'recording_identity': 'unavailable', 'checkpoint': None, 'accounting': None}
    try:
        with (out / 'manifest.json').open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError('invalid manifest')
        manifest = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, ValueError, RecursionError):
        return data
    if (type(manifest) is not dict or type(manifest.get('version')) is not int
            or manifest['version'] != _RECOVERY_VERSION or manifest.get('run_id') != run_id):
        data['recording_identity'] = 'mismatch'
        return data
    data.update(recording_identity='matched', checkpoint=_checkpoint(out, run_id), accounting=_accounting(out, run_id))
    return data


def save_receipt(out: Path, receipt: dict) -> Path:
    """A separate sibling receipt also covers cancellation before the child creates its output."""
    path = out.with_name(f'{out.name}.supervision-{receipt["run_id"]}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(receipt, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('ascii'))
        stream.flush()
        os.fsync(stream.fileno())
    return path
