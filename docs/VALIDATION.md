# Alpha validation

## Environment

Tested on glibc Void Linux with Python 3.14.7, Picard 2.13.3, Qt/PyQt5 5.15.11,
Mutagen 1.47.0 and the system `fpcalc`/ffmpeg builds. Other supported Python
versions are covered by the unit CI matrix, not by this local backend check.
Picard 3/Qt6 is deliberately rejected rather than assumed compatible.

## Automated coverage

The unit suite covers initialization, state isolation, album grouping, symlink
boundaries, command quoting, pause/resume, locks, deadlines, interrupted atomic
writes, failed workers, saved-journal recovery, exception retries, save accounting
and persistent overnight quotas. Exception tests cover collisions, candidate-only
read-only scans, legacy reports, diagnostic capture before cleanup, and preservation
of saved counts/timestamps/quotas during diagnosis. It makes no network requests and does not touch
real libraries.

The worker smoke check starts a real isolated Picard process, loads generated FLAC,
executes a command file and exits. It exercises configuration and runtime isolation,
but does not test a successful MusicBrainz match.

## Format checks

`tools/check_formats.py` generates 15-second sine-wave fixtures with ffmpeg. It
uses Picard's real format loaders/writers to change and reload title/artist tags,
then invokes `fpcalc` on the resulting file. A mock tagger object supplies UI
signals only; serialization is performed by Picard. This is not an end-to-end
lookup/scan/save test and does not test artwork or all possible tag variants.

| Format | Tag write/read | Fingerprint on this machine |
| --- | --- | --- |
| MP3 | Passed | Passed |
| M4A/AAC | Passed | Passed |
| FLAC | Passed | Passed |
| Ogg Vorbis | Passed | Passed |
| Opus | Passed | Passed |
| WAV | Passed | Converter error |
| AIFF | Passed | Converter error |
| ADTS AAC | Passed | Passed |
| WMA | Passed | Converter error |
| OGA/Ogg FLAC | Passed | Passed |
| WavPack | Passed | Passed |
| Monkey's Audio | Header-fixture tag roundtrip only | Full audio not validated |

The same WAV/AIFF/WMA converter errors occurred with both mono and stereo generated
fixtures. These formats remain available for metadata lookup; successful fingerprint
scanning depends on the user's codec build. Failure to match or save remains an
exception, not a successful tag. Do not treat a green `doctor` result as proof of
codec support. The format checker intentionally returns failure for this matrix
until the local fingerprint tool can process all selected fixtures.

APE recognition uses Picard's existing backend. Only a header-sized upstream
Mutagen test fixture was available during development; that is insufficient to
claim full audio/fingerprint validation. `--ape-fixture` accepts a real local file,
which is copied into a temporary directory before writing tags.

## Remaining user acceptance

Real MusicBrainz matching on a small copied library is the intended next test.
Check release choice, artwork retention, exceptions, stop/resume and overnight
behavior using docs/TESTING.md. No claim is made that every automatic release
match is correct. Public alpha status does not mean this acceptance is complete.
