import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from picard_batch import cli, migration, nightly, runner
from picard_batch.storage import lock, read, write_json


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.legacy = self.root / 'legacy'
        self.target = self.root / 'target'
        self.library = self.root / 'audio'
        self.library.mkdir()
        self.paths = [str(self.library / name) for name in ('a.mp3', 'b.mp3', 'c.mp3')]
        for path in self.paths:
            Path(path).touch()
        write_json(self.legacy / 'picard-progress.json', {'root': str(self.library),
                    'batches': [[p] for p in self.paths], 'done': [1]})
        write_json(self.legacy / 'picard-auto-work/progress.json', {'batches': {
            '2': {'saved': [], 'unresolved': [self.paths[1]], 'completed_at': 456}}})
        write_json(self.legacy / 'nightly.json', {'enabled': False})

    def test_import_preserves_manual_auto_and_partial_progress(self):
        journal = self.legacy / 'picard-auto-work/batch-0003-crash/saved.jsonl'
        journal.parent.mkdir()
        journal.write_text('{"path": "' + self.paths[2] + '"}\n')
        (self.legacy / 'picard-auto-work/STOP').touch()
        value = migration.import_legacy(self.legacy, self.target)
        self.assertEqual(len(value['batches']), 2)
        self.assertEqual(value['batches']['1']['confirmation'], 'legacy_manual')
        self.assertEqual(value['batches']['1']['saved'], [self.paths[0]])
        self.assertEqual(value['events'][0]['completed_at'], 456)
        self.assertEqual(read(self.target / 'library.json')['done'], [])
        self.assertTrue((self.target / 'work/STOP').exists())
        self.assertEqual((self.target / 'work/batch-0003-crash/saved.jsonl').read_bytes(), journal.read_bytes())
        with patch.object(runner, 'run_pass') as worker, contextlib.redirect_stderr(io.StringIO()):
            (self.target / 'work/STOP').unlink()
            runner.process(self.target / 'library.json', self.target / 'work', 1)
            worker.assert_not_called()
        self.assertEqual(len(cli.report(self.target)), 3)

    def test_existing_destination_is_not_overwritten(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            migration.import_legacy(self.legacy, self.target)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_running_legacy_watcher_is_not_imported(self):
        with lock(self.legacy / 'picard-auto-work/scheduler.lock'):
            with self.assertRaises(ValueError):
                migration.import_legacy(self.legacy, self.target)
        self.assertFalse(self.target.exists())

    def test_enabled_legacy_nightly_is_rejected(self):
        write_json(self.legacy / 'nightly.json', {'enabled': True})
        with self.assertRaisesRegex(ValueError, 'Disable'):
            migration.import_legacy(self.legacy, self.target)
        self.assertFalse(self.target.exists())

    def test_inconsistent_legacy_partition_is_rejected(self):
        write_json(self.legacy / 'picard-auto-work/progress.json', {'batches': {
            '2': {'saved': [self.paths[0]], 'unresolved': [], 'completed_at': 456}}})
        with self.assertRaisesRegex(ValueError, 'partition'):
            migration.import_legacy(self.legacy, self.target)
        self.assertFalse(self.target.exists())

    def test_failed_import_does_not_publish_partial_state(self):
        with patch.object(migration.os, 'rename', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                migration.import_legacy(self.legacy, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.root.glob('.picard-import-*')), [])


class Defaults(unittest.TestCase):
    def test_user_default_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / 'config/picard-batch/config.json', {'state_dir': str(root / 'personal')})
            write_json(root / 'test/library.json', {'root': str(root / 'audio'), 'batches': []})
            with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(root / 'config')}):
                self.assertEqual(cli.default_state(), root / 'personal')
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    cli.main(['--state-dir', str(root / 'test'), 'plan'])
                self.assertEqual(output.getvalue().strip(), '{}')

    def test_invalid_default_has_a_friendly_cli_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / 'picard-batch/config.json', {'state_dir': 123})
            with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(root)}), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.main(['status'])


class Nightly(unittest.TestCase):
    def test_enable_disable_preserves_settings_and_starts_one_watcher(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            (state / 'work').mkdir()
            (state / 'work/STOP').touch()
            with patch.object(nightly.subprocess, 'Popen') as spawn:
                nightly.enable(state, start=22, end=6, quota=7, timeout=90)
            self.assertFalse((state / 'work/STOP').exists())
            self.assertIn('--configured', spawn.call_args.args[0])
            self.assertTrue(read(state / 'nightly.json')['enabled'])
            nightly.disable(state)
            self.assertTrue((state / 'work/STOP').exists())
            self.assertFalse(read(state / 'nightly.json')['enabled'])
            with lock(state / 'scheduler.lock'), patch.object(nightly.subprocess, 'Popen') as spawn:
                nightly.enable(state)
                spawn.assert_not_called()
            value = nightly.settings(state)
            self.assertEqual((value['start'], value['end'], value['quota']), (22, 6, 7))

    def test_resume_does_not_reenable_disabled_nightly(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            write_json(state / 'library.json', {'root': folder, 'batches': []})
            nightly.disable(state)
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(['--state-dir', folder, 'resume'])
            self.assertFalse(nightly.settings(state)['enabled'])
            self.assertFalse((state / 'work/STOP').exists())

    def test_schedule_honors_disabled_nightly_without_starting_work(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            write_json(state / 'library.json', {'root': folder, 'batches': [['/a.mp3']]})
            nightly.disable(state)
            with patch.object(cli.doctor, 'require'), patch.object(cli, 'run') as run:
                with patch.object(cli.time, 'sleep', side_effect=KeyboardInterrupt), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(KeyboardInterrupt):
                        cli.schedule(state, 0, 6, 25, configured=True)
                run.assert_not_called()

    def test_invalid_nightly_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            write_json(state / 'nightly.json', {'enabled': 'yes'})
            with self.assertRaises(ValueError):
                nightly.settings(state)
