# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe backend capabilities without starting a GUI or tagging files."""
import json
import shutil
import subprocess
import sys

PROBE = '''
import json
import picard
from picard.util.remotecommands import REMOTE_COMMANDS
from picard.file import register_file_post_save_processor
from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
import picard.tagger
print(json.dumps({'picard': picard.__version__, 'qt': QT_VERSION_STR,
                  'pyqt': PYQT_VERSION_STR, 'commands': sorted(REMOTE_COMMANDS)}))
'''
REQUIRED = {'LOAD', 'CLUSTER', 'LOOKUP', 'SCAN', 'SAVE_MATCHED', 'REMOVE_SAVED',
            'REMOVE_EMPTY', 'REMOVE_ALL', 'WRITE_LOGS', 'QUIT', 'FROM_FILE'}


def check():
    errors = []
    info = {'python': sys.version.split()[0], 'interpreter': sys.executable,
            'fpcalc': shutil.which('fpcalc')}
    try:
        process = subprocess.run([sys.executable, '-c', PROBE], capture_output=True,
                                 text=True, timeout=20)
        if process.returncode:
            errors.append('Cannot import the Picard/PyQt5 backend in this interpreter. '
                          'Install Picard 2.9–2.x and use a venv with --system-site-packages. '
                          + (process.stderr.strip().splitlines() or ['No diagnostic output.'])[-1])
        else:
            backend = json.loads(process.stdout.splitlines()[-1])
            info.update({k: v for k, v in backend.items() if k != 'commands'})
            if not backend['picard'].startswith('2.'):
                errors.append('This alpha supports Picard 2.x with PyQt5; Picard 3/Qt6 is not supported yet.')
            missing = REQUIRED - set(backend['commands'])
            if missing:
                errors.append('Picard lacks required commands: ' + ', '.join(sorted(missing)))
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError) as error:
        errors.append('Backend probe failed: ' + str(error))
    if not info['fpcalc']:
        errors.append('fpcalc is missing. Install Chromaprint fingerprint tools and add fpcalc to PATH.')
    return info, errors


def require():
    _, errors = check()
    if errors:
        raise ValueError('\n'.join(errors) + '\nRun picard-batch doctor for details.')
