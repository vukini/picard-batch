# SPDX-License-Identifier: GPL-2.0-or-later
"""Import the original music-tagger state without rescanning or rewriting audio."""
import os
from pathlib import Path
import shutil
import tempfile

from .diagnostics import detailed_report
from .storage import lock, read, write_json


def import_legacy(source, destination):
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not (source / 'picard-progress.json').is_file():
        raise ValueError('Legacy installation does not contain picard-progress.json.')
    if destination.exists():
        raise ValueError('Import destination already exists; choose a new --state-dir.')
    work = source / 'picard-auto-work'
    # Freeze both kinds of legacy writers while taking the migration snapshot.
    # The caller must first disable the legacy nightly watcher.
    with lock(work / 'scheduler.lock'), lock(work / 'runner.lock'):
        nightly = read(source / 'nightly.json') if (source / 'nightly.json').exists() else {}
        if nightly.get('enabled', False):
            raise ValueError('Disable the legacy nightly watcher before importing.')
        library = read(source / 'picard-progress.json')
        batches = library['batches']
        root = Path(library['root']).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('Legacy library root does not exist.')
        if not batches or any(not isinstance(b, list) or not b for b in batches):
            raise ValueError('Invalid legacy batch list.')
        all_paths = [p for batch in batches for p in batch]
        if len(set(all_paths)) != len(all_paths):
            raise ValueError('Legacy inventory contains duplicate paths.')
        for path in all_paths:
            if not isinstance(path, str) or not Path(path).is_absolute() or not Path(path).is_relative_to(root):
                raise ValueError('Legacy inventory contains paths outside its library root.')
        legacy = read(work / 'progress.json') if (work / 'progress.json').exists() else {'batches': {}}
        result = {'batches': {}, 'events': []}
        for number, batch in legacy['batches'].items():
            if not str(number).isdigit() or not 1 <= int(number) <= len(batches):
                raise ValueError('Invalid completed legacy batch number.')
            expected = set(batches[int(number)-1])
            saved, unresolved = set(batch['saved']), set(batch['unresolved'])
            if saved & unresolved or saved | unresolved != expected:
                raise ValueError(f'Legacy saved/unresolved paths do not partition batch {number}.')
            result['batches'][str(number)] = batch
            result['events'].append({'batch': int(number), 'retry': False,
                                     'completed_at': batch.get('completed_at', 0), 'imported': True})
        for number in library.get('done', []):
            if not isinstance(number, int) or not 1 <= number <= len(batches):
                raise ValueError('Invalid manually confirmed legacy batch number.')
            if str(number) not in result['batches']:
                result['batches'][str(number)] = {
                    'saved': batches[number-1], 'unresolved': [], 'completed_at': 0,
                    'confirmation': 'legacy_manual',
                }
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.picard-import-', dir=destination.parent))
        try:
            write_json(stage / 'library.json', {**library, 'root': str(root), 'schema': 1,
                                                'done': [], 'imported_from': str(source)})
            write_json(stage / 'work/progress.json', result)
            write_json(stage / 'work/exceptions.json',
                       {n: b['unresolved'] for n, b in result['batches'].items() if b['unresolved']})
            write_json(stage / 'work/exception-details.json', detailed_report(result['batches']))
            # Preserve durable writes from unfinished/crashed legacy batches too.
            for journal in work.glob('batch-*/saved.jsonl'):
                target = stage / 'work' / journal.parent.name / journal.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(journal, target)
            if (work / 'STOP').exists():
                (stage / 'work/STOP').touch()
            write_json(stage / 'migration.json', {'legacy_installation': str(source),
                                                 'audio_files': len(all_paths),
                                                 'manual_confirmation_time': 'unknown; represented by 0'})
            os.rename(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return result
