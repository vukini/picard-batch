import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from picard_batch import cli, doctor, inventory, runner
from picard_batch.storage import read, write_json


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / 'audio'
        self.library.mkdir()
        self.paths = []
        for name in ('a.mp3', 'b.mp3'):
            path = self.library / name
            path.touch()
            self.paths.append(str(path))
        self.state = self.root / 'state'
        with contextlib.redirect_stdout(io.StringIO()):
            cli.initialize(self.state, self.library, 100)
        self.work = self.state / 'work'

    def process(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            runner.process(self.state / 'library.json', self.work, 1,
                           retry_rounds=0, retry_delay=0, **kwargs)

    def test_partial_save_recovered_after_crash(self):
        folder = self.work / 'batch-0001-interrupted'
        folder.mkdir(parents=True)
        (folder / 'saved.jsonl').write_text(json.dumps({'path': self.paths[0]}) + '\n{"path":')
        with patch.object(runner, 'run_pass', side_effect=lambda paths, *a, **k: set(paths)) as worker:
            self.process()
        self.assertEqual(worker.call_args.args[0], [self.paths[1]])
        self.assertEqual(set(cli.report(self.state)['1']['saved']), set(self.paths))

    def test_retry_does_not_rewrite_saved_tracks(self):
        with patch.object(runner, 'run_pass', return_value={self.paths[0]}):
            self.process()
        self.assertEqual(cli.exceptions(self.state), {'1': [self.paths[1]]})
        with patch.object(runner, 'run_pass', side_effect=lambda paths, *a, **k: set(paths)) as worker:
            self.process(retry=True)
        self.assertEqual(worker.call_args.args[0], [self.paths[1]])
        self.assertEqual(cli.exceptions(self.state), {})
        value = cli.progress(self.state)
        self.assertEqual(len(value['events']), 2)
        self.assertTrue(value['events'][-1]['retry'])

    def test_pause_arriving_during_batch_prevents_next(self):
        value = read(self.state / 'library.json')
        value['batches'] = [[p] for p in self.paths]
        write_json(self.state / 'library.json', value)
        def save(paths, *args, **kwargs):
            (self.work / 'STOP').touch()
            return set(paths)
        with patch.object(runner, 'run_pass', side_effect=save) as worker:
            with contextlib.redirect_stdout(io.StringIO()):
                runner.process(self.state / 'library.json', self.work, 5)
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(len(cli.report(self.state)), 1)

    def test_failed_atomic_replace_preserves_previous_state(self):
        path = self.root / 'report.json'
        write_json(path, {'old': True})
        with patch('picard_batch.storage.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                write_json(path, {'new': True})
        self.assertEqual(read(path), {'old': True})
        self.assertEqual(list(self.root.glob('.report.json*')), [])

    def test_missing_file_does_not_advance(self):
        Path(self.paths[0]).unlink()
        with self.assertRaises(RuntimeError):
            self.process()
        self.assertEqual(cli.report(self.state), {})

    def test_unexpected_worker_save_is_never_counted(self):
        with patch.object(runner, 'run_pass', return_value={'/unrelated.mp3'}):
            self.process()
        self.assertEqual(cli.report(self.state)['1']['saved'], [])

    def test_quota_counts_retries_and_survives_restart(self):
        begin, end = cli.window(datetime(2026, 10, 21, 2), 0, 6)
        value = {'batches': {}, 'events': [{'completed_at': begin.timestamp()+1}]*3}
        write_json(self.root / 'quota.json', value)
        self.assertEqual(cli.remaining_quota(read(self.root / 'quota.json'), begin, end, 5), 2)
        self.assertEqual(cli.remaining_quota(value, begin, end, 1), 0)

    def test_preview_creates_no_state(self):
        target = self.root / 'preview'
        with contextlib.redirect_stdout(io.StringIO()):
            cli.initialize(target, self.library, 100, preview=True)
        self.assertFalse(target.exists())

    def test_album_groups_not_split_and_multidisc_combined(self):
        with patch.object(inventory, 'album_key', return_value=('album', 'artist', 'release')):
            batches, _ = inventory.inventory(self.library, 1)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)

    def test_symlinks_outside_library_are_excluded(self):
        outside = self.root / 'outside.mp3'
        outside.touch()
        (self.library / 'link.mp3').symlink_to(outside)
        batches, skipped = inventory.inventory(self.library, 100)
        self.assertEqual(skipped, 1)
        self.assertEqual(sum(map(len, batches)), 2)

    def test_same_library_uses_same_lock_for_different_states(self):
        other = self.root / 'another-state'
        other.mkdir()
        write_json(other / 'library.json', read(self.state / 'library.json'))
        self.assertEqual(cli.library_lock(self.state), cli.library_lock(other))

    def test_export_refuses_overwrite(self):
        output = self.root / 'export.json'
        output.write_text('original')
        with self.assertRaises(SystemExit):
            cli.main(['--state-dir', str(self.state), 'exceptions', '--output', str(output)])
        self.assertEqual(output.read_text(), 'original')

    def test_command_quoting_and_newline_rejection(self):
        text = runner.commands(["/music/O'Brien song.mp3"], self.root / 'finished.log')
        import shlex
        self.assertEqual(shlex.split(text.splitlines()[0])[1], "/music/O'Brien song.mp3")
        with self.assertRaises(ValueError):
            runner.commands(['/music/bad\nname.mp3'], self.root / 'done')

    def test_doctor_reports_missing_backend_and_fingerprint_tool(self):
        import subprocess
        result = subprocess.CompletedProcess([], 1, '', 'ModuleNotFoundError: picard')
        with patch.object(doctor.subprocess, 'run', return_value=result), patch.object(doctor.shutil, 'which', return_value=None):
            info, errors = doctor.check()
        self.assertEqual(len(errors), 2)
        self.assertIsNone(info['fpcalc'])


if __name__ == '__main__':
    unittest.main()
