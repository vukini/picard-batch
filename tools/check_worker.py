#!/usr/bin/env python3
"""Offline worker startup/load/command-file smoke test on generated FLAC audio."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from picard_batch import runner

with tempfile.TemporaryDirectory(prefix='picard-batch-worker-') as folder:
    root = Path(folder)
    audio = root / "test song's audio.flac"
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=1', str(audio)], check=True, timeout=30)
    commands = root / 'commands.txt'
    finished = root / 'finished.log'
    commands.write_text('LOAD ' + shlex.quote(str(audio)) + '\nCLUSTER\nWRITE_LOGS '
                        + shlex.quote(str(finished)) + '\nREMOVE_ALL\nQUIT force\n')
    environment = os.environ.copy()
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    with (root / 'process.log').open('w') as log:
        result = subprocess.run([sys.executable, str(runner.HERE / 'worker.py'),
                                 str(root / 'isolated.ini'), str(commands), str(root / 'saves.jsonl')],
                                env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    if result.returncode or not finished.exists():
        print((root / 'process.log').read_text(), file=sys.stderr)
        raise SystemExit('Worker smoke test failed.')
    import json
    details = json.loads((root / 'details.json').read_text())
    assert str(audio) in details, 'Worker did not capture reasons before cleanup.'
    assert not (root / 'saves.jsonl').exists(), 'Read-only worker unexpectedly saved audio.'
    print('Worker started, loaded generated FLAC, executed commands and exited successfully.')
