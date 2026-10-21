# SPDX-License-Identifier: GPL-2.0-or-later
"""Sequential isolated Picard workers, durable saves and resumable batches."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

from .storage import lock, read, write_json
from .progress import WorkerProgress, emit

HERE = Path(__file__).resolve().parent


def commands(paths, finished, scan=False):
    if any('\n' in p or '\r' in p for p in paths):
        raise ValueError('A filename contains a newline; cannot encode Picard commands.')
    lines = ['LOAD ' + shlex.quote(p) for p in paths]
    lines += ['SCAN'] if scan else ['CLUSTER', 'LOOKUP clustered']
    lines += ['SAVE_MATCHED', 'REMOVE_SAVED', 'REMOVE_EMPTY', 'REMOVE_ALL',
              'WRITE_LOGS ' + shlex.quote(str(finished)), 'QUIT force']
    return '\n'.join(lines) + '\n'


def scan_commands(paths, finished):
    return commands(paths, finished, scan=True)


def journal_paths(path):
    if not path.exists():
        return set()
    saved = set()
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        try:
            saved.add(json.loads(line)['path'])
        except (ValueError, KeyError, TypeError):
            # A power loss can leave one unfinished final journal entry.
            if index != len(lines)-1:
                raise ValueError(f'Corrupt save journal: {path}') from None
    return saved


def run_pass(paths, folder, scan=False, timeout=1800):
    folder.mkdir(parents=True, exist_ok=False)
    finished = folder / 'finished.log'
    command_path = folder / 'commands.txt'
    command_path.write_text(commands(paths, finished, scan))
    environment = os.environ.copy()
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    with (folder / 'process.log').open('w') as log:
        process = subprocess.Popen(
            [sys.executable, '-u', str(HERE / 'worker.py'), str(folder / 'Picard.ini'),
             str(command_path), str(folder / 'saved.jsonl')],
            env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        monitor = WorkerProgress(folder, len(paths), journal_paths)
        emit(f'Worker log: {folder / "process.log"}')
        monitor.start()
        try:
            process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            if isinstance(error, KeyboardInterrupt):
                raise
            raise RuntimeError(f'Worker timed out; saved journals retained. See {folder / "process.log"}.') from None
        finally:
            monitor.close()
    if process.returncode or not finished.exists():
        raise RuntimeError(f'Picard did not finish; see {folder / "process.log"}. Restart resumes this batch.')
    return journal_paths(folder / 'saved.jsonl') & set(paths)


def process(state_path, work, count, deadline=None, retry=False, timeout=1800,
            retry_rounds=2, retry_delay=60):
    work.mkdir(parents=True, exist_ok=True)
    with lock(work / 'runner.lock'):
        state = read(state_path)
        report_path = work / 'progress.json'
        report = read(report_path) if report_path.exists() else {'batches': {}, 'events': []}
        # Migrate first-alpha progress without losing quota history.
        if 'events' not in report:
            report['events'] = [{'completed_at': b['completed_at']} for b in report['batches'].values()]
        completed = 0
        for number, original in enumerate(state['batches'], 1):
            if deadline is not None and time.time() >= deadline:
                emit('Time window ended; no new batch started.')
                break
            if (work / 'STOP').exists():
                emit('Pause requested; no new batch started.')
                break
            if completed >= count:
                break
            previous = report['batches'].get(str(number))
            if retry:
                if not previous or not previous['unresolved']:
                    continue
                paths = previous['unresolved']
            else:
                if number in state.get('done', []) or previous:
                    continue
                paths = original
            if any(not Path(p).is_file() for p in paths):
                raise RuntimeError(f'Missing files in batch {number}; stopped without advancing.')
            emit(f'Batch {number}/{len(state["batches"])}: {len(paths)} files')
            saved = set(previous['saved']) if previous else set()
            # Recover actual successful writes even if a worker failed before its final report.
            for journal in work.glob(f'batch-{number:04}-*/saved.jsonl'):
                saved |= journal_paths(journal) & set(original)
            if saved:
                emit(f'Recovered/retained {len(saved)} confirmed saves for this batch.')
            stamp = time.time_ns()
            for attempt in range(retry_rounds + 1):
                if set(paths) <= saved:
                    break
                if attempt:
                    emit(f'Waiting {retry_delay}s before retry {attempt}/{retry_rounds}: '
                         f'{len(set(paths)-saved)} files unresolved.')
                    time.sleep(retry_delay)
                for scan in (False, True):
                    remaining = [p for p in paths if p not in saved]
                    if not remaining:
                        break
                    phase = 'Fingerprint scan' if scan else 'Album lookup'
                    emit(f'{phase}: {len(remaining)} files; attempt {attempt+1}/{retry_rounds+1}.')
                    folder = work / f'batch-{number:04}-{stamp}-{attempt}-{int(scan)}'
                    saved |= run_pass(remaining, folder, scan, timeout=timeout) & set(paths)
                    emit(f'{phase} finished: {len(saved)}/{len(original)} batch files confirmed saved; '
                         f'{len(set(paths)-saved)} still unresolved.')
            exceptions = [p for p in original if p not in saved]
            now = time.time()
            report['batches'][str(number)] = {'saved': sorted(saved), 'unresolved': exceptions,
                                             'completed_at': now}
            report['events'].append({'batch': number, 'retry': retry, 'completed_at': now})
            write_json(report_path, report)
            # Convenience export: progress.json is the authoritative state.
            write_json(work / 'exceptions.json',
                       {n: b['unresolved'] for n, b in report['batches'].items() if b['unresolved']})
            emit(f'Batch {number} complete: {len(saved)} saved; {len(exceptions)} unresolved. Progress recorded.')
            completed += 1
        emit(f'Run finished: {completed} batches. Reports: {work}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--max-batches', type=int, default=5)
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args(argv)
    process(args.state, args.work, args.max_batches, args.deadline)
