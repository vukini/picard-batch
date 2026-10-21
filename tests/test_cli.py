import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from picard_batch import cli, runner


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / 'music'
        self.library.mkdir()
        for name in ('one/a.mp3', 'two/b.flac', 'ignore.txt'):
            path = self.library / name
            path.parent.mkdir(exist_ok=True)
            path.touch()
        self.state = self.root / 'state'
        self.call('init', str(self.library), '--batch-size', '1')

    def call(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.main(['--state-dir', str(self.state), *args])

    def test_initialization_is_explicit_and_not_overwritten(self):
        original = (self.state / 'library.json').read_bytes()
        self.assertEqual(len(json.loads(original)['batches']), 2)
        with self.assertRaises(SystemExit):
            self.call('init', str(self.library))
        self.assertEqual(original, (self.state / 'library.json').read_bytes())
        self.assertFalse((self.library / 'picard-progress.json').exists())

    def test_pause_requires_resume(self):
        self.call('pause')
        with patch.object(cli, 'run') as run:
            with self.assertRaises(SystemExit):
                self.call('run', '1')
            run.assert_not_called()
            self.call('resume')
            self.call('run', '1')
            run.assert_called_once_with(self.state, 1, retry=False, timeout=1800)

    def test_runner_resumes_and_preserves_exceptions(self):
        argv = ['--state', str(self.state / 'library.json'), '--work', str(self.state / 'work'),
                '--max-batches', '1']
        with patch.object(runner, 'run_pass', side_effect=lambda paths, folder, scan, **kwargs: set(paths)):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main(argv)
                runner.main(argv)
        self.assertEqual(len(cli.report(self.state)), 2)
        with patch.object(runner, 'run_pass') as worker:
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main(argv)
            worker.assert_not_called()

    def test_crash_does_not_advance_batch(self):
        with patch.object(runner, 'run_pass', side_effect=RuntimeError('worker failed')):
            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                runner.main(['--state', str(self.state / 'library.json'),
                             '--work', str(self.state / 'work')])
        self.assertEqual(cli.report(self.state), {})

    def test_deadline_does_not_start_worker(self):
        with patch.object(runner, 'run_pass') as worker:
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main(['--state', str(self.state / 'library.json'),
                             '--work', str(self.state / 'work'), '--deadline', '0'])
            worker.assert_not_called()

    def test_library_lock_is_exclusive(self):
        with cli.lock(self.root / 'lock'):
            with self.assertRaises(ValueError):
                with cli.lock(self.root / 'lock'):
                    self.fail('second lock acquired')

    def test_overnight_window(self):
        for hour, expected_start_day, expected_end_day in ((23, 21, 22), (2, 20, 21)):
            begin, end = cli.window(datetime(2026, 10, 21, hour), 22, 6)
            self.assertEqual(begin.day, expected_start_day)
            self.assertEqual(end.day, expected_end_day)
            self.assertLess(begin, end)


if __name__ == '__main__':
    unittest.main()
