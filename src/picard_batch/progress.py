# SPDX-License-Identifier: GPL-2.0-or-later
"""Live progress on stderr; stdout remains available for command results."""
from datetime import datetime
from pathlib import Path
import sys
import threading
import time


def emit(message):
    print(f'[{datetime.now():%H:%M:%S}] {message}', file=sys.stderr, flush=True)


class WorkerProgress:
    """Follow worker logs and confirmed saves without blocking its wait/timeout."""

    def __init__(self, folder, total, journal_reader, interval=15):
        self.folder = Path(folder)
        self.total = total
        self.journal_reader = journal_reader
        self.interval = interval
        self.started = time.monotonic()
        self.last_message = self.started
        self.offset = 0
        self.pending = ''
        self.saved = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.follow, name='picard-progress', daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join()

    def poll(self, final=False):
        now = time.monotonic()
        log = self.folder / 'process.log'
        if log.exists():
            with log.open(errors='replace') as stream:
                stream.seek(self.offset)
                self.pending += stream.read()
                self.offset = stream.tell()
            lines = self.pending.split('\n')
            self.pending = lines.pop()
            if final and self.pending:
                lines.append(self.pending)
                self.pending = ''
            for line in lines:
                if line.strip() and 'This plugin does not support propagateSizeHints()' not in line:
                    emit('Picard: ' + line.rstrip())
        saved = len(self.journal_reader(self.folder / 'saved.jsonl'))
        if saved != self.saved:
            self.saved = saved
            emit(f'Confirmed saves in this pass: {saved}/{self.total} ({int(now-self.started)}s elapsed).')
            self.last_message = now
        if not final and now-self.last_message >= self.interval:
            emit(f'Still working: {int(now-self.started)}s elapsed; '
                 f'{self.saved}/{self.total} confirmed saves in this pass.')
            self.last_message = now

    def follow(self):
        try:
            while not self.stop.wait(1):
                self.poll()
            self.poll(final=True)
        except (OSError, ValueError) as error:
            # Observability must never interfere with tagging or save journals.
            emit(f'Could not follow worker progress: {error}. Logs remain in {self.folder}.')
