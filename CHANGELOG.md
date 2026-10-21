# Changelog

## 0.1.0a4

- Import original music-tagger progress, manual confirmations, exceptions and interrupted-save journals without rescanning audio.
- Add persistent `night-on`/`night-off` controls and configured background watchers.
- Preserve nightly quotas and distinguish imported manual confirmations from confirmed automatic writes.

## 0.1.0a3

- Explain unresolved files with per-file reasons and matched recording/release details.
- Report multiple files attached to the same album track without weakening automatic-save safeguards.
- Add `exceptions --details` while preserving the existing path-only JSON output.
- Add read-only `diagnose [N]` to refresh exception reasons without saving tags or changing quotas.
- Capture worker diagnostics before cleanup removes track associations.

## 0.1.0a2

- Stream timestamped batch, pass, save and retry-wait progress to stderr.
- Forward Picard diagnostics live while retaining the full worker log.
- Emit a 15-second heartbeat during quiet lookup/scan operations.
- Keep stdout clean for JSON and command results; retain worker cleanup on interruption.

## 0.1.0a1

Initial Linux testing alpha:

- Installable CLI with explicit library and XDG state directories.
- Album/directory-aware inventory and dry-run plans.
- Confirmed-save journals, atomic progress, crash recovery and per-library locking.
- Bounded runs, pause/resume, exception export and explicit retries.
- Configurable overnight windows and persistent quota accounting.
- Backend diagnostics and worker timeout/termination cleanup.
- Recognition of OGA, WavPack and Monkey's Audio alongside common music formats.

Requires a compatible Picard 2.x/PyQt5 installation. Picard 3/Qt6, Windows and
macOS are outside the supported scope of this alpha.
