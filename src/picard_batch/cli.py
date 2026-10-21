# SPDX-License-Identifier: GPL-2.0-or-later
"""Resumable MusicBrainz Picard batch tagging."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import signal
import threading
import time

from . import __version__, doctor, runner
from .inventory import FORMATS, inventory
from .storage import lock, locked, read, write_json


def default_state():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'picard-batch'


def initialize(state, library, size, preview=False):
    library = library.expanduser().resolve()
    if not library.is_dir():
        raise ValueError('Library must be an existing directory.')
    batches, skipped = inventory(library, size)
    if not batches:
        raise ValueError('No supported audio files found.')
    value = {'schema': 1, 'root': str(library), 'done': [], 'batch_size': size,
             'batches': batches}
    if preview:
        print(json.dumps(value, indent=2))
        return
    with lock(state / 'init.lock'):
        target = state / 'library.json'
        if target.exists():
            raise ValueError('State already initialized; choose a different --state-dir.')
        write_json(target, value)
    print(f'Initialized {sum(map(len, batches))} files in {len(batches)} batches.')
    oversized = sum(len(b) > size for b in batches)
    if oversized:
        print(f'{oversized} batches exceed the target size to preserve album/directory groups.')
    if skipped:
        print(f'Skipped {skipped} symlinks leading outside the library.')


def library_lock(state):
    library = read(state / 'library.json')['root']
    identity = hashlib.sha256(library.encode()).hexdigest()
    # A fixed per-user namespace prevents different --state-dir values bypassing the lock.
    return Path.home() / '.local/state/picard-batch/locks' / (identity + '.lock')


def run(state, count, deadline=None, retry=False, timeout=1800):
    doctor.require()
    with lock(library_lock(state)):
        runner.process(state / 'library.json', state / 'work', count,
                       deadline=deadline, retry=retry, timeout=timeout)


def window(now, start, end):
    begin = now.replace(hour=start, minute=0, second=0, microsecond=0)
    finish = now.replace(hour=end, minute=0, second=0, microsecond=0)
    if end <= start:
        if now < finish:
            begin -= timedelta(days=1)
        else:
            finish += timedelta(days=1)
    return begin, finish


def progress(state):
    path = state / 'work/progress.json'
    return read(path) if path.exists() else {'batches': {}, 'events': []}


def report(state):
    return progress(state)['batches']


def remaining_quota(value, begin, finish, quota):
    events = value.get('events', list(value['batches'].values()))
    used = sum(begin.timestamp() <= b.get('completed_at', 0) < finish.timestamp()
               for b in events)
    return max(0, quota-used)


def schedule(state, start, end, quota, timeout=1800):
    doctor.require()
    with lock(state / 'scheduler.lock'):
        print(f'Watcher active: {start:02}:00–{end:02}:00, quota {quota}.', flush=True)
        while True:
            now = datetime.now()
            begin, finish = window(now, start, end)
            value = progress(state)
            if len(value['batches']) >= len(read(state / 'library.json')['batches']):
                print('All batches processed; review exceptions separately.')
                return
            remaining = remaining_quota(value, begin, finish, quota)
            if begin <= now < finish and remaining and not (state / 'work/STOP').exists():
                try:
                    run(state, remaining, finish.timestamp(), timeout=timeout)
                except (ValueError, RuntimeError, OSError) as error:
                    print(str(error), file=sys.stderr, flush=True)
                time.sleep(300)
            time.sleep(30)


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError('Must be at least 1.')
    return value


def exceptions(state):
    return {n: b['unresolved'] for n, b in report(state).items() if b['unresolved']}


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--state-dir', type=Path, default=default_state(),
                        help='Runtime directory (default: XDG_STATE_HOME/picard-batch).')
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init', help='Freeze an explicit library list; never writes audio tags.')
    init.add_argument('library', type=Path)
    init.add_argument('--batch-size', type=positive, default=100,
                      help='Target files per batch; album groups may exceed this.')
    init.add_argument('--dry-run', action='store_true', help='Print inventory JSON without creating state.')
    for action, help_text in [('run', 'Tag unprocessed batches.'), ('retry', 'Retry only unresolved files in processed batches.')]:
        start = sub.add_parser(action, help=help_text)
        start.add_argument('batches', type=positive, nargs='?', default=5)
        start.add_argument('--worker-timeout', type=positive, default=1800,
                           help='Maximum seconds per lookup/scan worker (default: 1800).')
    sub.add_parser('doctor', help='Check backend imports, command support and fpcalc.')
    sub.add_parser('formats', help='List recognized audio extensions.')
    sub.add_parser('status')
    sub.add_parser('plan', help='Show pending batches as JSON without tagging.')
    sub.add_parser('pause', help='Stop after the current batch.')
    sub.add_parser('resume', help='Clear pause without starting a runner.')
    export = sub.add_parser('exceptions', help='Show or export unresolved files.')
    export.add_argument('--output', type=Path, help='Write JSON to a new file; refuses to overwrite.')
    sched = sub.add_parser('schedule', help='Run overnight watcher in foreground.')
    sched.add_argument('--start-hour', type=int, choices=range(24), default=0)
    sched.add_argument('--end-hour', type=int, choices=range(24), default=6)
    sched.add_argument('--quota', type=positive, default=25)
    sched.add_argument('--worker-timeout', type=positive, default=1800)
    args = parser.parse_args(argv)
    state = args.state_dir.expanduser().resolve()
    try:
        if args.action == 'doctor':
            info, errors = doctor.check()
            print(json.dumps({'backend': info, 'errors': errors}, indent=2))
            return 1 if errors else 0
        if args.action == 'formats':
            for extension, name in sorted(FORMATS.items()):
                print(f'{extension:7} {name}')
            return 0
        if args.action == 'init':
            initialize(state, args.library, args.batch_size, args.dry_run)
            return 0
        if not (state / 'library.json').exists():
            raise ValueError('State not initialized. Run init LIBRARY first.')
        if args.action in ('run', 'retry'):
            if (state / 'work/STOP').exists():
                raise ValueError('Paused. Run resume before starting another batch.')
            run(state, args.batches, retry=args.action == 'retry', timeout=args.worker_timeout)
        elif args.action == 'schedule':
            if args.start_hour == args.end_hour:
                raise ValueError('Start and end hours must differ.')
            schedule(state, args.start_hour, args.end_hour, args.quota, args.worker_timeout)
        elif args.action in ('pause', 'resume'):
            (state / 'work').mkdir(exist_ok=True)
            stop = state / 'work/STOP'
            if args.action == 'pause':
                stop.touch()
                print('Pause requested; current batch will finish.')
            else:
                stop.unlink(missing_ok=True)
                print('Pause cleared.')
        elif args.action == 'exceptions':
            text = json.dumps(exceptions(state), indent=2) + '\n'
            if args.output:
                with args.output.expanduser().open('x') as stream:
                    stream.write(text)
            else:
                print(text, end='')
        elif args.action == 'plan':
            done = report(state)
            batches = read(state / 'library.json')['batches']
            print(json.dumps({n: paths for n, paths in enumerate(batches, 1) if str(n) not in done}, indent=2))
        else:
            batches = report(state)
            total = len(read(state / 'library.json')['batches'])
            print(f'{len(batches)}/{total} batches processed')
            print(f'{sum(len(b["saved"]) for b in batches.values())} saved; '
                  f'{sum(len(b["unresolved"]) for b in batches.values())} exceptions')
            print('Runner:', 'active' if locked(library_lock(state)) else 'idle')
            print('Watcher:', 'active' if locked(state / 'scheduler.lock') else 'stopped')
            print('Paused:', (state / 'work/STOP').exists())
            print('State:', state)
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        parser.exit(1, f'picard-batch: {error}\n')
    except KeyboardInterrupt:
        return 130


def main(argv=None):
    # Terminating the CLI must also reap its isolated worker before releasing locks.
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    if threading.current_thread() is not threading.main_thread():
        return _main(argv)
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        return _main(argv)
    finally:
        signal.signal(signal.SIGTERM, previous)
