"""Bound a live child process independently of its event loop."""
from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import time
from typing import Sequence


@dataclass(frozen=True)
class SupervisionResult:
    status: str
    exit_code: int
    child_exit_code: int


def _kill_and_reap(child) -> int:
    while True:
        try:
            if child.poll() is None:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass  # The worker exited between the poll and the kill.
            return child.wait()
        except KeyboardInterrupt:
            # A second interrupt must not leave the paid worker running.
            continue


def supervise_command(argv: Sequence[str], *, timeout_seconds: float = 240.0,
                      cleanup_seconds: float = 5.0, control_pipe: bool = False) -> SupervisionResult:
    """Stop and reap this child on deadline or interruption. Live workers cancel on pipe EOF."""
    if not argv or not 0 < timeout_seconds <= 3600 or not 0 < cleanup_seconds <= 5:
        raise ValueError('Invalid supervised command or deadline')
    kwargs = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    deadline = time.monotonic() + timeout_seconds
    child = subprocess.Popen(list(argv), stdin=subprocess.PIPE if control_pipe else None, **kwargs)
    try:
        try:
            code = child.wait(timeout=max(0., deadline - time.monotonic()))
            return SupervisionResult('completed' if code == 0 else 'child_failed', code, code)
        except subprocess.TimeoutExpired:
            status, exit_code = 'wall_timeout', 124
        except KeyboardInterrupt:
            status, exit_code = 'interrupted', 130
        cleanup_deadline = time.monotonic() + cleanup_seconds
        try:
            if control_pipe:
                child.stdin.close()
            elif os.name == 'nt':
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(child.pid, signal.SIGINT)
            code = child.wait(timeout=max(0., cleanup_deadline - time.monotonic()))
        except (subprocess.TimeoutExpired, OSError, ValueError, KeyboardInterrupt):
            code = _kill_and_reap(child)
        return SupervisionResult(status, exit_code, code)
    except BaseException:
        _kill_and_reap(child)
        raise
    finally:
        if control_pipe and not child.stdin.closed:
            child.stdin.close()
