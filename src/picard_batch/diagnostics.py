# SPDX-License-Identifier: GPL-2.0-or-later
"""Explain unresolved files without weakening Picard's save safeguards."""


def unknown():
    return {'reason': 'not_recorded',
            'message': 'No reason was recorded by this version. Run diagnose to inspect without saving.'}


def describe(file, read_only=False, network_errors=False):
    parent = file.parent
    linked = getattr(parent, 'num_linked_files', 0)
    result = {'network_errors_in_pass': network_errors}
    if file.has_error():
        result.update(reason='file_error', message='Picard reported a file read/write/processing error; see the worker log.')
    elif linked > 1:
        result.update(reason='multiple_files_same_track',
                      message=f'{linked} files matched the same album track; automatic saving was skipped.',
                      conflicting_files=[f.filename for f in parent.files])
    elif linked == 1:
        result.update(reason='candidate_found' if read_only else 'not_saved',
                      message='A candidate track was found; this diagnostic did not save it.' if read_only else
                              'A track was matched but no successful save was confirmed; see the worker log.')
    else:
        result.update(reason='no_match', message='No unique album-track match was confirmed.')
    if file.metadata['musicbrainz_recordingid']:
        result['recording'] = file.metadata['musicbrainz_recordingid']
    if file.metadata['musicbrainz_albumid']:
        result['release'] = file.metadata['musicbrainz_albumid']
    if network_errors:
        result['network_note'] = 'Network errors occurred during this pass; inspect its log before judging the match.'
    return result


def collect(tagger, folder, read_only=False):
    log = folder / 'process.log'
    network_errors = log.exists() and 'Network request error' in log.read_text(errors='replace')
    return {file.filename: describe(file, read_only, network_errors) for file in tagger.files.values()}


def detailed_report(batches):
    return {n: [{'path': path, **batch.get('reasons', {}).get(path, unknown())}
                for path in batch['unresolved']]
            for n, batch in batches.items() if batch['unresolved']}
