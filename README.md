# Picard Batch

Resumable, album-aware batch tagging for large music libraries, powered by
MusicBrainz Picard. Run a few batches now, pause after the current batch, or leave
a watcher to work within an overnight window.

**Linux testing alpha.** Requires Picard 2.9–2.x with PyQt5. Picard 3/Qt6,
Windows and macOS are not supported by this release. This is an independent
companion, not an official MusicBrainz or MetaBrainz product.

## Install

Install Python 3.10+, MusicBrainz Picard 2.x and Chromaprint's `fpcalc` through
your distribution. Those backend dependencies must be visible to the Python
interpreter used below; they are not installed by this package.

```sh
git clone https://github.com/vukini/picard-batch.git
cd picard-batch
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
picard-batch doctor
```

`doctor` checks Picard/PyQt5 imports, the command interface, and the presence of
`fpcalc`. It exits nonzero with an explanation if the backend is unavailable.
It does not test MusicBrainz connectivity or every codec. A Flatpak/AppImage
Picard executable alone does not provide importable modules to this environment.

## First run

Start with **copies in a separate test library** and keep an independent backup.
Tagging writes into audio files, and there is no metadata rollback.

```sh
# Inspect the proposed inventory without creating state or changing audio.
picard-batch init /path/to/test-library --dry-run

# Freeze the library list and process one batch.
picard-batch init /path/to/test-library --batch-size 100
picard-batch plan
picard-batch run 1
picard-batch status
picard-batch exceptions
```

The batch size is a **target**, not a hard maximum. Tracks sharing a release MBID,
or an album and album artist, stay together across folders/discs. When tags are
missing, the parent directory is kept together. A large group can exceed the
batch target. Inspect `plan` before running, especially for untagged flat folders.
Video and M4B audiobooks are excluded. Symlinks outside the library are skipped.

## Commands

| Command | Behavior |
| --- | --- |
| `init LIBRARY [--batch-size 100] [--dry-run]` | Inventory an explicit library; refuses to replace existing state |
| `doctor` | Report backend versions and missing dependencies |
| `formats` | List recognized file extensions |
| `plan` | Print pending batches and paths as JSON; no tagging |
| `run [N]` | Process up to N unfinished batches; defaults to 5 |
| `status` | Show saved/unresolved counts, active runner/watcher and pause state |
| `pause` | Finish the current batch, then stop starting new ones |
| `resume` | Clear pause without starting work |
| `exceptions [--output NEW_FILE]` | Print/export unresolved paths as JSON; never overwrites an export |
| `retry [N]` | Retry unresolved files in up to N completed batches, retaining confirmed saves |
| `schedule [options]` | Run the overnight watcher in the foreground |

`run` and `retry` require `resume` after a pause. They accept
`--worker-timeout SECONDS` (default 1800 per lookup/scan pass). A batch may contain
multiple passes, including two retry rounds with 60-second waits. `retry` is
explicit: normal runs and the watcher skip completed batches with exceptions.

## Live progress and logs

`run`, `retry` and `schedule` write timestamped progress to **stderr**, flushed
immediately: batch/pass starts, confirmed saves during a pass, retry delays and
completion. Picard diagnostics (including HTTP errors) are forwarded live. During
a quiet worker, a heartbeat appears every 15 seconds with elapsed time and confirmed
saves. Full logs are still retained under the state's `work/batch-*/process.log`.

`status` counts completed batches; in-progress confirmed saves appear in the live
progress before they are committed to the batch report. A 60-second retry wait is
announced before it begins. An existing running command keeps the logging behavior
of the version it started with; updates apply to subsequent invocations.

Stdout remains available for JSON/output commands. To keep a separate live log:

```sh
picard-batch run 1 2>run-progress.log
```

## Overnight runs

```sh
picard-batch schedule --start-hour 0 --end-hour 6 --quota 25
```

Times use the computer's local timezone. Windows crossing midnight are supported,
for example `--start-hour 22 --end-hour 6`. The watcher starts no new batch after
the end time and lets a running batch finish. The quota counts completed batches,
including manual and retry runs within the window, and survives restarts.
This is a batch quota; album-aware groups mean it is not an exact track limit.

Keep the machine awake and online. No login rule, daemon or service is installed.
Use another terminal to `pause`. For a graceful stop, wait until `status` shows
an idle runner before ending the watcher. Ctrl-C or SIGTERM during a worker
terminates that worker; confirmed saves are recovered on the next run.

## State, recovery and multiple libraries

State defaults to `$XDG_STATE_HOME/picard-batch`, falling back to
`~/.local/state/picard-batch`. It is independent of installed code. For another
library, choose another state directory on **every command**:

```sh
picard-batch --state-dir /path/to/second-state init /path/to/second-library
picard-batch --state-dir /path/to/second-state run 1
```

Keep `library.json` and `work/` together. `work/progress.json` is authoritative;
`exceptions.json` is a convenience export. Each pass retains its Picard log,
configuration, command file and successful-save journal under `work/batch-*`.
There is no automatic log deletion. Treat state files as private: they contain
library paths and identifiers; do not commit them or attach them without review.

Progress is replaced atomically. A failed worker leaves its batch unfinished;
a restart recovers confirmed writes from journals and retries the remainder.
Missing input paths stop processing without advancing. Do not rename files or
modify tags with another program while processing. Refreshing an existing frozen
inventory is not supported yet; do not delete current state to force a rescan.

A per-user lock prevents two packaged runners for the same canonical library
root, even when they use different state directories. It does not coordinate
with Picard's GUI, other tagging programs, another user, overlapping parent/child
roots or the original personal scripts. Use one tool on a library at a time.
Workers use separate Picard settings, runtime pipes and caches.

## Matching and formats

Each batch tries album lookup followed by fingerprint scanning, with bounded
retries. Only confirmed successful saves are counted. Similarity thresholds are
0.9 for file lookup and 0.85 for album and track matching; these are scores, not
probabilities of correctness. Review the results before expanding a run.

Moving, renaming, tagger scripts and artwork downloads are disabled; existing
artwork is preserved. Existing tags can be replaced by matched MusicBrainz data.
Fingerprints are used for lookup, not submitted. There is no transcoding.

Recognized formats: MP3, M4A, FLAC, Ogg Vorbis, Opus, WAV, AIFF, AAC, WMA,
OGA/Ogg FLAC, WavPack and Monkey's Audio. Recognition is not a guarantee that a
particular codec build can fingerprint a file. See [validation and known
limitations](docs/VALIDATION.md) for the tested matrix. Monkey's Audio is
experimental in this alpha. Other Picard formats can be added after validation.

## Development and license

```sh
./check.sh
# Optional system-backend checks on generated files; no network lookups:
PYTHONPATH=src python3 tools/check_worker.py
python3 tools/check_formats.py
```

The unit suite uses temporary fixture files and mocked workers. The optional
format check writes tags to generated audio, then tests fingerprinting separately;
it returns nonzero for unsupported operations. See [TESTING.md](docs/TESTING.md)
for an end-to-end checklist and [ROADMAP.md](ROADMAP.md) for later releases.

Licensed under **GPL-2.0-or-later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Picard, Qt, Mutagen and system codecs retain their own licenses.
