"""Check committed changes using the GitHub event's comparison boundary."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main() -> int:
    try:
        event = os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch')
        path = os.environ.get('GITHUB_EVENT_PATH')
        payload = json.loads(Path(path).read_text(encoding='utf-8')) if path else {}
        if event == 'pull_request':
            base = payload['pull_request']['base']['sha']
        elif event == 'push':
            base = payload['before']
        else:
            parent = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD^'],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            base = parent.stdout.strip() if parent.returncode == 0 else '0' * 40
        if not isinstance(base, str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', base):
            raise ValueError('Invalid comparison commit')
        if event != 'pull_request':
            present = subprocess.run(['git', 'cat-file', '-e', base + '^{commit}'],
                                     capture_output=True).returncode == 0
            if not present:
                # Initial/root commits and unavailable pre-force-push history.
                base = subprocess.check_output(
                    ['git', 'hash-object', '-w', '-t', 'tree', '--stdin'],
                    input='', text=True, encoding='utf-8', errors='replace').strip()
        comparison = [base + '...HEAD'] if event == 'pull_request' else [base, 'HEAD']
        print('Checking committed diff:', ' '.join(comparison), flush=True)
        return subprocess.run(['git', 'diff', '--check', *comparison]).returncode
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'Committed diff check failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
