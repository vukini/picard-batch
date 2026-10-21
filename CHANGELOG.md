# Changelog

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
