# Test the alpha

Use a separate folder of copied music, outside the library processed by any other
runner. The tool writes tags in place. Keep originals and the test state so you
can compare and resume. No test requires changing your current personal setup.

1. Install using the README and run `picard-batch doctor`.
2. Choose an absolute test-state path. Prefix every command with
   `picard-batch --state-dir /path/to/test-state`.
3. Run `init /path/to/copied-library --dry-run`. Check that tracks from the same
   album remain together. A folder with no useful tags is one group.
4. Run `init /path/to/copied-library --batch-size 20`, then `plan` and `status`.
5. Run `run 1`. Inspect the copied audio in Picard or another tag viewer. Confirm
   release choice, title, artist and retained artwork. Check originals separately
   if desired; only the copies should change.
6. Run `exceptions`, and `exceptions --output /path/to/new-report.json`. An empty
   object means every processed input had a confirmed save, not that all matches
   are necessarily the correct edition.
7. Run `retry 1` if exceptions exist. Confirm previous successful saves remain
   accounted for and unresolved counts reflect the retry.
8. In one terminal run `run 5`; in another run `pause`. The current batch finishes,
   then no new batch starts. Run `resume`, then `run 1` to continue.
9. Start `schedule` with a suitable local start/end hour and `--quota 1`. Check
   that it respects the window and quota. `pause` stops new work without disabling
   the foreground watcher. End an idle watcher with Ctrl-C.
10. Preserve logs for any failure. Review/redact library paths before opening a
    public issue. Include the package version, `doctor` output and the failed
    command; do not upload your audio or private progress wholesale.

For format-specific investigation:

```sh
python3 tools/check_formats.py --only flac mp3
python3 tools/check_formats.py --only ape --ape-fixture /path/to/real-test.ape
```

These checks work on temporary copies/generated files and perform no online
lookup. Their output separates tag serialization from fingerprint capability.
