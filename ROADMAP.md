# Roadmap

## 0.1 alpha: implemented for user testing

- Installable CLI and explicit library/state configuration.
- Album-aware batching with directory fallback, inventory preview and plans.
- Backend diagnostics for Picard 2.x/PyQt5 and fpcalc.
- Per-library locking, atomic progress and journal recovery.
- Exception listing/export and explicit retries.
- Configurable nightly windows, quotas and worker timeout cleanup.
- Common formats plus OGA, WavPack and experimental Monkey's Audio recognition.
- Unit coverage, real worker startup check, format checks, documentation and GPL license.

See docs/VALIDATION.md for actual results and remaining user acceptance; the
implemented alpha is not a guarantee of codec support or correct release matching.

## After alpha feedback

- Address results from copied-library lookup/scan/save acceptance tests.
- Investigate local fpcalc converter failures and validate real APE audio.
- Validate Picard 3/Qt6 with a separate backend adapter.
- Add safe inventory refresh and stronger overlapping-root coordination.
- Add further formats (AIFC, Musepack, TTA, TAK, OptimFROG and DSD) with fixtures.
- Consider opt-in scheduling integration and Windows/macOS portability.
- Consider M4B/chapter-aware audiobook handling separately from music tagging.
