import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from picard_batch import doctor, inventory, runner


class Worker(unittest.TestCase):
    def test_timeout_terminates_and_reaps_worker(self):
        process = Mock(pid=123456)
        process.wait.side_effect = [subprocess.TimeoutExpired('worker', 1), 0]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner.subprocess, 'Popen', return_value=process), patch.object(runner.os, 'killpg') as kill:
                with self.assertRaisesRegex(RuntimeError, 'timed out'):
                    runner.run_pass(['/test.flac'], Path(folder) / 'pass', timeout=1)
            kill.assert_called_once_with(123456, runner.signal.SIGTERM)
            self.assertEqual(process.wait.call_count, 2)

    def test_keyboard_interrupt_cleans_worker_and_propagates(self):
        process = Mock(pid=123456)
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner.subprocess, 'Popen', return_value=process), patch.object(runner.os, 'killpg') as kill:
                with self.assertRaises(KeyboardInterrupt):
                    runner.run_pass(['/test.flac'], Path(folder) / 'pass')
            kill.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)

    def test_hung_worker_is_killed_after_termination_timeout(self):
        process = Mock(pid=123456)
        process.wait.side_effect = [subprocess.TimeoutExpired('worker', 1),
                                    subprocess.TimeoutExpired('worker', 10), 0]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(runner.subprocess, 'Popen', return_value=process), patch.object(runner.os, 'killpg') as kill:
                with self.assertRaises(RuntimeError):
                    runner.run_pass(['/test.flac'], Path(folder) / 'pass', timeout=1)
            self.assertEqual(kill.call_args.args, (123456, runner.signal.SIGKILL))
            self.assertEqual(process.wait.call_count, 3)

    def test_album_metadata_groups_discs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('disc1/one.flac', 'disc2/two.flac'):
                path = root / name
                path.parent.mkdir()
                path.touch()
            tags = {'album': ['A record'], 'albumartist': ['An artist']}
            with patch.object(inventory.mutagen, 'File', return_value=tags):
                batches, _ = inventory.inventory(root, 1)
            self.assertEqual(len(batches), 1)
            self.assertEqual(len(batches[0]), 2)

    def test_rejects_qt6_backend_with_explicit_message(self):
        import json
        backend = {'picard': '3.0', 'qt': '6', 'pyqt': '6', 'commands': list(doctor.REQUIRED)}
        process = subprocess.CompletedProcess([], 0, json.dumps(backend), '')
        with patch.object(doctor.subprocess, 'run', return_value=process), patch.object(doctor.shutil, 'which', return_value='/fpcalc'):
            _, errors = doctor.check()
        self.assertTrue(any('Picard 3/Qt6' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
