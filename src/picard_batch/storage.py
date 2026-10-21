# SPDX-License-Identifier: GPL-2.0-or-later
"""Atomic state files and process locks (Linux)."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


def read(path):
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as error:
        raise ValueError(f'Cannot read state {path}: {error}') from error


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name, delete=False) as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f'Another process holds {path}') from None
        yield


def locked(path):
    if not path.exists():
        return False
    try:
        with lock(path):
            return False
    except ValueError:
        return True
