#!/usr/bin/env python3
"""Offline format checks using generated audio; no personal files or network calls.

Requires system Picard 2.x, PyQt5, ffmpeg and fpcalc. An optional --ape-fixture
is copied to a temporary directory before testing (ffmpeg cannot encode APE).
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import Mock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ape-fixture', type=Path)
    parser.add_argument('--channels', type=int, choices=(1, 2), default=2)
    parser.add_argument('--only', nargs='+', help='Restrict checks to extensions without dots.')
    args = parser.parse_args()
    from PyQt5.QtCore import QCoreApplication
    import picard.tagger  # Registers Picard's configuration defaults.
    from picard import config
    from picard.file import File
    from picard.formats import open_
    app = QCoreApplication([])
    # Format serialization does not need a running tagger or its UI signals.
    File.tagger = Mock()
    cases = [('mp3', 'libmp3lame'), ('m4a', 'aac'), ('flac', 'flac'),
             ('ogg', 'libvorbis'), ('opus', 'libopus'), ('wav', 'pcm_s16le'),
             ('aiff', 'pcm_s16be'), ('aac', 'aac'), ('wma', 'wmav2'),
             ('oga', 'flac'), ('wv', 'wavpack')]
    results = []
    with tempfile.TemporaryDirectory(prefix='picard-batch-formats-') as folder:
        root = Path(folder)
        config.setup_config(app, str(root / 'isolated.ini'))
        config.setting['clear_existing_tags'] = False
        config.setting['save_images_to_tags'] = False
        for extension, codec in cases:
            if args.only and extension not in args.only:
                continue
            path = root / ('fixture.' + extension)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=15', '-ac', str(args.channels), '-c:a', codec, str(path)],
                           check=True, timeout=30)
            results.append(check(path, open_))
        if args.ape_fixture:
            path = root / 'fixture.ape'
            shutil.copyfile(args.ape_fixture, path)
            results.append(check(path, open_))
    print(json.dumps(results, indent=2))
    if not results:
        parser.error('No formats selected; APE requires --ape-fixture.')
    return 0 if all(row['tag_roundtrip'] and row['fingerprint'] for row in results) else 1


def check(path, open_):
    row = {'extension': path.suffix, 'tag_roundtrip': False, 'fingerprint': False}
    try:
        file = open_(str(path))
        metadata = file._load(str(path))
        metadata['title'] = 'Disposable format verification'
        metadata['artist'] = 'Picard Batch test fixture'
        file._save(str(path), metadata)
        row['tag_roundtrip'] = file._load(str(path))['title'] == metadata['title']
    except Exception as error:
        row['tag_error'] = str(error)
    process = subprocess.run(['fpcalc', '-json', str(path)], capture_output=True,
                             text=True, timeout=30)
    try:
        # Some fpcalc builds warn at EOF even after emitting a usable fingerprint.
        value = json.loads(process.stdout)
        row['fingerprint'] = value.get('duration', 0) >= 10 and len(value.get('fingerprint', '')) > 6
        if not row['fingerprint']:
            row['fingerprint_error'] = 'Insufficient decoded audio or fingerprint data.'
    except (ValueError, KeyError):
        row['fingerprint_error'] = process.stderr.strip()
    return row


if __name__ == '__main__':
    raise SystemExit(main())
