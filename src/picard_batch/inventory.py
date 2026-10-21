# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only inventory; preserve tagged albums or directory groups."""
from collections import defaultdict
from pathlib import Path
import mutagen

FORMATS = {
    '.mp3': 'MP3', '.m4a': 'MPEG-4 audio', '.flac': 'FLAC', '.ogg': 'Ogg Vorbis',
    '.opus': 'Ogg Opus', '.wav': 'WAVE', '.aif': 'AIFF', '.aiff': 'AIFF',
    '.aac': 'ADTS AAC', '.wma': 'Windows Media Audio', '.oga': 'Ogg audio',
    '.wv': 'WavPack', '.ape': "Monkey's Audio",
}


def album_key(path):
    try:
        tags = mutagen.File(path, easy=True)
        if tags is not None:
            release = tags.get('musicbrainz_albumid', [])
            if release:
                return ('release', str(release[0]))
            album = tags.get('album', [])
            artist = tags.get('albumartist', []) or tags.get('artist', [])
            if album and artist:
                return ('album', str(artist[0]).casefold(), str(album[0]).casefold())
    except (mutagen.MutagenError, OSError, ValueError, TypeError):
        pass
    return ('directory', str(path.parent))


def inventory(library, size):
    groups = defaultdict(list)
    seen = set()
    skipped = 0
    for original in sorted(library.rglob('*')):
        if not original.is_file() or original.suffix.lower() not in FORMATS:
            continue
        path = original.resolve()
        if not path.is_relative_to(library):
            skipped += 1
            continue
        if path in seen:
            continue
        if '\n' in str(path) or '\r' in str(path):
            raise ValueError(f'Filename contains a newline: {path!s}')
        seen.add(path)
        groups[album_key(path)].append(str(path))
    batches = []
    batch = []
    for paths in groups.values():
        if batch and len(batch) + len(paths) > size:
            batches.append(batch)
            batch = []
        batch.extend(paths)
        if len(batch) >= size:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)
    return batches, skipped
