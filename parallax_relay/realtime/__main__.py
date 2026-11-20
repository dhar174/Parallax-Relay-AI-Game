"""Run, watch or verify one development match from the checkout root."""
from __future__ import annotations

import argparse
from decimal import Decimal
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from threading import Thread, Timer
from uuid import uuid4

from pydantic import ValidationError

from ..budget import Budget
from ..config import ConfigError
from ..protocol import ROLES
from .journal import replay
from .observations import observe
from .physics import initial_world
from .recovery import interruption_receipt, save_receipt
from .server import SpectatorServer, serve
from .settings import Settings, describe_profile, load_profile
from .supervise import supervise_command
from .wire import make_request


def check_profile(profile):
    """Quote the actual opening broadcast without credentials, clients or calls."""
    data = describe_profile(profile)
    settings = profile.settings
    world = initial_world()
    requests = {
        role: make_request(observe(world, role, 1, settings), 'broadcast', (), [], '', 1,
                           '0' * 32, settings)
        for role in ROLES
    }
    budget = Budget(settings, profile.rates)
    tickets = budget.reserve_phase(requests)
    data['first_phase_reserved_usd'] = str(budget.reserved_usd)
    data['headroom_after_first_reservation_usd'] = str(Decimal(str(settings.max_estimated_cost_usd)) - budget.reserved_usd)
    for ticket in tickets.values():
        ticket.release()
    data['calls_started'] = budget.calls_started
    return data


def _parent_control(session, cleanup_seconds):
    # An anonymous pipe is available even to a Windows child without a console.
    # EOF means the parent revoked this run or exited unexpectedly.
    try:
        os.read(sys.stdin.fileno(), 1)
    except (OSError, ValueError):
        pass
    # If the supervisor itself died, nobody else can enforce this child's
    # grace period. Keep the watchdog armed until ordinary process exit.
    watchdog = Timer(cleanup_seconds, os._exit, args=(125,))
    watchdog.daemon = True
    watchdog.start()
    session.close()


def _run(out, mode, settings, profile, spectate, latency='demo', run_id=None):
    from .session import Session
    session = Session(out, mode, settings, profile=profile, latency=latency, run_id=run_id)
    print(f'Recording: {out.resolve()}', flush=True)
    if spectate and mode != 'live':
        def new_session():
            destination = out.with_name(f'{out.name}-restart-{uuid4().hex[:8]}')
            replacement = Session(destination, mode, settings, latency=latency)
            print(f'Recording: {destination.resolve()}', flush=True)
            return replacement

        serve(session, new_session=new_session)
        return 0
    try:
        if mode == 'live':
            # Only the CLI starts a paid match. Its viewer follows the bounded run.
            Thread(target=_parent_control, args=(session, settings.cleanup_seconds),
                   name='parallax-parent-control', daemon=True).start()
            server = SpectatorServer(session)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            print(f'Open {server.url} in your browser.', flush=True)
        if not session.start():
            return 130
        result = session.wait()
        print(json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        session.close()
        if mode == 'live' and 'server' in locals():
            server.shutdown()
            server.server_close()
    reason = result['stop_reason']
    if reason in ('checkpoint', 'window_limit', 'victory', 'turn_limit', 'time_limit'):
        return 0
    if reason in ('call_budget', 'spend_budget'):
        return 4
    return 2 if reason == 'local_error' else 3


def _live_child():
    # The public CLI always supervises this invocation. Only validated fixed
    # profile settings are used; credentials stay in the provider environment.
    profile = load_profile(sys.argv[1])
    return _run(Path(sys.argv[2]), 'live', profile.settings, profile, True, run_id=sys.argv[3])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline', choices=('reactive', 'manual', 'baseline', 'test'))
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--verify-record', type=Path, metavar='DIRECTORY')
    parser.add_argument('--profile', choices=('dev-bridge-live-v1',))
    parser.add_argument('--spectate', action='store_true', help='Wait for Start in the interactive loopback viewer.')
    parser.add_argument('--out', type=Path, help='Fresh recording directory.')
    parser.add_argument('--clock', dest='clock_mode', choices=('freeze', 'continue'))
    parser.add_argument('--window-ticks', type=int)
    parser.add_argument('--windows', type=int, dest='max_windows')
    parser.add_argument('--action-points', type=int)
    parser.add_argument('--phase-timeout', type=float, dest='phase_timeout_seconds')
    parser.add_argument('--communication-rounds', type=int, choices=(1, 2))
    parser.add_argument('--latency', choices=('demo', 'historical'), default='demo',
                        help='Replay the nine measured call delays in the offline HTTP fixture.')
    args = parser.parse_args(argv)
    overrides = {k: getattr(args, k) for k in ('clock_mode', 'window_ticks', 'max_windows',
                'action_points', 'phase_timeout_seconds', 'communication_rounds') if getattr(args, k) is not None}
    if bool(args.profile) != bool(args.check or args.live):
        parser.error('--check and --live require a named profile')
    if overrides and args.offline not in ('reactive', 'manual', 'test'):
        parser.error('Physics tuning flags require an offline physics run')
    if (args.check or args.verify_record) and (args.spectate or args.out):
        parser.error('Verification takes no run or spectator options')
    if args.offline == 'manual' and not args.spectate:
        parser.error('Manual controls require --spectate')
    if args.latency == 'historical' and args.offline != 'test':
        parser.error('--latency historical requires --offline test')
    try:
        if args.verify_record:
            print(json.dumps(replay(args.verify_record), indent=2))
            return 0
        if args.check:
            print(json.dumps(check_profile(load_profile(args.profile)), indent=2))
            return 0
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        out = args.out or Path('runs') / f'realtime_{stamp}_{uuid4().hex[:8]}'
        if args.live:
            profile = load_profile(args.profile)
            if out.exists() or out.is_symlink():
                raise FileExistsError('A live recording requires a fresh destination')
            run_id = str(uuid4())
            command = [sys.executable, '-c', 'from parallax_relay.realtime.__main__ import _live_child; '
                       'raise SystemExit(_live_child())', profile.name, str(out), run_id]
            outcome = supervise_command(command, timeout_seconds=profile.settings.wall_seconds,
                                        cleanup_seconds=profile.settings.cleanup_seconds, control_pipe=True)
            if outcome.status in ('interrupted', 'wall_timeout'):
                receipt = interruption_receipt(out, run_id, outcome)
                try:
                    saved = str(save_receipt(out, receipt).resolve())
                except OSError:
                    saved = None
                print(json.dumps({'supervision': receipt, 'receipt_file': saved}, ensure_ascii=True), flush=True)
            return outcome.exit_code
        defaults = Settings.offline(args.offline).model_dump()
        defaults.update(overrides)
        # Offline trials may use additional windows but remain limited at every phase.
        defaults['max_calls'] = defaults['max_windows'] * (defaults['communication_rounds'] + 1) * len(ROLES)
        return _run(out, args.offline, Settings.model_validate(defaults), None, args.spectate, args.latency)
    except KeyboardInterrupt:
        return 130
    except (ConfigError, ValueError, ValidationError, OSError, RuntimeError, KeyError) as exc:
        print(f'Local configuration, recording or verification failed ({type(exc).__name__}).', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
