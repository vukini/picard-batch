import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from picard_batch import cli, diagnostics, runner
from picard_batch.storage import read, write_json


def file(parent, error=False):
    return SimpleNamespace(parent=parent, has_error=lambda: error, filename='/test.mp3',
                           metadata={'musicbrainz_recordingid': 'recording-id',
                                     'musicbrainz_albumid': 'release-id'})


class Diagnostics(unittest.TestCase):
    def test_collision_explains_why_automatic_save_is_skipped(self):
        parent = SimpleNamespace(num_linked_files=2,
                                 files=[SimpleNamespace(filename='/a.mp3'), SimpleNamespace(filename='/b.mp3')])
        result = diagnostics.describe(file(parent))
        self.assertEqual(result['reason'], 'multiple_files_same_track')
        self.assertEqual(result['conflicting_files'], ['/a.mp3', '/b.mp3'])
        self.assertEqual(result['recording'], 'recording-id')
        self.assertIn('automatic saving was skipped', result['message'])

    def test_unique_readonly_match_is_candidate_not_a_save(self):
        parent = SimpleNamespace(num_linked_files=1)
        self.assertEqual(diagnostics.describe(file(parent), read_only=True)['reason'], 'candidate_found')
        self.assertEqual(diagnostics.describe(file(parent))['reason'], 'not_saved')

    def test_file_errors_and_unmatched_files_are_distinguished(self):
        self.assertEqual(diagnostics.describe(file(None, error=True))['reason'], 'file_error')
        result = diagnostics.describe(file(None), network_errors=True)
        self.assertEqual(result['reason'], 'no_match')
        self.assertTrue(result['network_errors_in_pass'])
        self.assertIn('Network errors occurred', result['network_note'])

    def test_old_progress_remains_readable_with_explicit_unknown_reason(self):
        batches = {'1': {'unresolved': ['/a.mp3'], 'saved': []}}
        result = diagnostics.detailed_report(batches)
        self.assertEqual(result['1'][0]['reason'], 'not_recorded')
        self.assertEqual(result['1'][0]['path'], '/a.mp3')

    def test_snapshot_precedes_cleanup_and_readonly_commands_cannot_save(self):
        text = runner.commands(['/a.mp3'], Path('/finished.log')).splitlines()
        self.assertLess(text.index('WRITE_LOGS /finished.log'), text.index('REMOVE_ALL'))
        readonly = runner.commands(['/a.mp3'], Path('/finished.log'), scan=True, read_only=True).splitlines()
        self.assertIn('SCAN', readonly)
        self.assertFalse(any(line.startswith('SAVE') for line in readonly))

    def test_diagnosis_preserves_counts_timestamps_and_quotas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'a.mp3'
            audio.touch()
            work = root / 'work'
            previous = {'batches': {'1': {'saved': ['/already-saved.mp3'],
                                         'unresolved': [str(audio)], 'completed_at': 123}},
                        'events': [{'batch': 1, 'completed_at': 123}]}
            write_json(work / 'progress.json', previous)
            detail = {'reason': 'multiple_files_same_track', 'message': 'Conflict; manual review required.'}
            def inspect(paths, pass_folder, **kwargs):
                self.assertTrue(kwargs['read_only'])
                self.assertTrue(kwargs['scan'])
                write_json(pass_folder / 'details.json', {str(audio): detail})
                return set()
            with patch.object(runner, 'run_pass', side_effect=inspect), contextlib.redirect_stderr(io.StringIO()):
                runner.diagnose(root / 'library.json', work, 1)
            updated = read(work / 'progress.json')
            self.assertEqual(updated['events'], previous['events'])
            self.assertEqual(updated['batches']['1']['saved'], previous['batches']['1']['saved'])
            self.assertEqual(updated['batches']['1']['unresolved'], [str(audio)])
            self.assertEqual(updated['batches']['1']['completed_at'], 123)
            self.assertEqual(updated['batches']['1']['reasons'][str(audio)], detail)
            self.assertEqual(cli.exceptions(root), {'1': [str(audio)]})
            self.assertEqual(cli.exceptions(root, details=True)['1'][0]['reason'], detail['reason'])

    def test_worker_reasons_reach_batch_report_and_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'a.mp3'
            audio.touch()
            write_json(root / 'library.json', {'batches': [[str(audio)]], 'done': []})
            detail = {'reason': 'multiple_files_same_track', 'message': 'Two files matched the same track.'}
            def inspect(paths, pass_folder, *args, **kwargs):
                write_json(pass_folder / 'details.json', {str(audio): detail})
                return set()
            stderr = io.StringIO()
            with patch.object(runner, 'run_pass', side_effect=inspect), contextlib.redirect_stderr(stderr):
                runner.process(root / 'library.json', root / 'work', 1, retry_rounds=0)
            self.assertIn(detail['message'], stderr.getvalue())
            self.assertEqual(read(root / 'work/exception-details.json')['1'][0]['reason'], detail['reason'])


if __name__ == '__main__':
    unittest.main()
