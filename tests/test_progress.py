import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from picard_batch.progress import WorkerProgress, emit
from picard_batch import cli, runner
from picard_batch.storage import write_json


class Progress(unittest.TestCase):
    def test_progress_is_flushed_to_stderr_only(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            emit('Album lookup: 5 files.')
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('Album lookup: 5 files.', stderr.getvalue())

    def test_idle_worker_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('picard_batch.progress.time.monotonic', return_value=0):
                monitor = WorkerProgress(folder, 5, lambda path: set())
            stderr = io.StringIO()
            with patch('picard_batch.progress.time.monotonic', return_value=15), contextlib.redirect_stderr(stderr):
                monitor.poll()
            self.assertIn('Still working: 15s elapsed; 0/5', stderr.getvalue())

    def test_network_errors_stream_once_and_partial_lines_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'process.log'
            log.write_text('E: HTTP 503\npartial')
            monitor = WorkerProgress(folder, 5, lambda path: set())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                monitor.poll()
                with log.open('a') as stream:
                    stream.write(' message\n')
                monitor.poll()
                monitor.poll(final=True)
            self.assertEqual(stderr.getvalue().count('HTTP 503'), 1)
            self.assertIn('partial message', stderr.getvalue())

    def test_confirmed_saves_appear_before_pass_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor = WorkerProgress(folder, 5, lambda path: {'one.mp3', 'two.mp3'})
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                monitor.poll()
                monitor.poll()
            self.assertIn('Confirmed saves in this pass: 2/5', stderr.getvalue())
            self.assertEqual(stderr.getvalue().count('Confirmed saves'), 1)

    def test_batch_progress_and_retry_wait_do_not_pollute_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'test.flac'
            audio.touch()
            write_json(root / 'library.json', {'batches': [[str(audio)]], 'done': []})
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(runner, 'run_pass', return_value=set()), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                runner.process(root / 'library.json', root / 'work', 1,
                               retry_rounds=1, retry_delay=0)
            self.assertEqual(stdout.getvalue(), '')
            for expected in ('Album lookup', 'Fingerprint scan', 'Waiting 0s before retry 1/1',
                             'Batch 1 complete', 'Run finished'):
                self.assertIn(expected, stderr.getvalue())

    def test_real_worker_output_is_forwarded_on_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'worker.py').write_text(
                'from pathlib import Path\nimport sys\n'
                'print("fixture worker message", flush=True)\n'
                '(Path(sys.argv[1]).parent / "finished.log").write_text("done")\n')
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(runner, 'HERE', root), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = runner.run_pass(['/fixture.flac'], root / 'pass', timeout=5)
            self.assertEqual(result, set())
            self.assertEqual(stdout.getvalue(), '')
            self.assertIn('Picard: fixture worker message', stderr.getvalue())

    def test_status_json_commands_stay_on_stdout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / 'library.json', {'root': str(root), 'batches': [], 'done': []})
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                cli.main(['--state-dir', str(root), 'exceptions'])
            self.assertEqual(stdout.getvalue().strip(), '{}')
            self.assertEqual(stderr.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
