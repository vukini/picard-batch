# SPDX-License-Identifier: GPL-2.0-or-later
#!/usr/bin/env python3
"""Isolated Picard instance with a journal of actual successful saves."""
import json
import os
import sys
from pathlib import Path

config_path, commands_path, saved_path = map(Path, sys.argv[1:4])
# Isolate runtime pipes and caches as well as Picard.ini. No desktop instance or
# user configuration is used by a batch worker.
for variable, name in [('XDG_RUNTIME_DIR', 'runtime'), ('XDG_CONFIG_HOME', 'config'),
                       ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data')]:
    directory = config_path.parent / name
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ[variable] = str(directory.resolve())

from PyQt5.QtCore import QSettings
from picard.file import register_file_post_save_processor
settings = QSettings(str(config_path), QSettings.IniFormat)
for name, value in {
    'rename_files': False, 'move_files': False, 'save_images_to_files': False,
    'save_images_to_tags': False, 'enable_tagger_scripts': False,
    'clear_existing_tags': False, 'preserve_images': True, 'analyze_new_files': False,
    'cluster_new_files': False, 'file_lookup_threshold': 0.9,
    'cluster_lookup_threshold': 0.85, 'track_matching_threshold': 0.85,
    'show_new_user_dialog': False, 'check_for_updates': False,
    'browser_integration': False,
}.items():
    settings.setValue('setting/' + name, value)
settings.sync()


def saved(file):
    # Picard calls this hook after the write succeeds, never on a save error.
    with saved_path.open('a') as stream:
        stream.write(json.dumps({'path': file.filename,
                                 'recording': file.metadata['musicbrainz_recordingid'],
                                 'release': file.metadata['musicbrainz_albumid']}) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


register_file_post_save_processor(saved)
sys.argv = ['picard', '-s', '-P', '-M', '--no-crash-dialog', '-c', str(config_path),
            '-e', 'FROM_FILE', str(commands_path)]
from picard.tagger import main
main('/usr/share/locale', False)
