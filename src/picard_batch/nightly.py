# SPDX-License-Identifier: GPL-2.0-or-later
"""Persistent nightly enablement; the watcher still uses the normal runner locks."""
import subprocess
import sys

from .storage import lock, locked, read, write_json

DEFAULTS = {'enabled': True, 'start': 0, 'end': 6, 'quota': 25, 'timeout': 1800}


def settings(state):
    path = state / 'nightly.json'
    value = {**DEFAULTS, **(read(path) if path.exists() else {})}
    if not isinstance(value['enabled'], bool):
        raise ValueError('Nightly enabled must be true or false.')
    for key in ('start', 'end', 'quota', 'timeout'):
        if not isinstance(value[key], int) or isinstance(value[key], bool):
            raise ValueError(f'Nightly {key} must be an integer.')
    if not (0 <= value['start'] <= 23 and 0 <= value['end'] <= 23) or value['start'] == value['end']:
        raise ValueError('Nightly start/end must be different hours from 0 through 23.')
    if value['quota'] < 1 or value['timeout'] < 1:
        raise ValueError('Nightly quota and timeout must be positive.')
    return value


def enable(state, **overrides):
    with lock(state / 'nightly-control.lock'):
        value = settings(state)
        value.update({key: val for key, val in overrides.items() if val is not None})
        # Validate before publishing or starting a background process.
        if value['start'] == value['end']:
            raise ValueError('Start and end hours must differ.')
        value['enabled'] = True
        write_json(state / 'nightly.json', value)
        (state / 'work/STOP').unlink(missing_ok=True)
        if not locked(state / 'scheduler.lock'):
            with (state / 'nightly.log').open('a') as log:
                subprocess.Popen([sys.executable, '-m', 'picard_batch', '--state-dir', str(state),
                                  'schedule', '--configured'], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return value


def disable(state):
    with lock(state / 'nightly-control.lock'):
        value = settings(state)
        value['enabled'] = False
        write_json(state / 'nightly.json', value)
        (state / 'work').mkdir(exist_ok=True)
        (state / 'work/STOP').touch()
    return value
