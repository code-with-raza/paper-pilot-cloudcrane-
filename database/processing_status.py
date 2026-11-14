"""Owner-scoped processing status. Never return raw provider errors or secrets."""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from database.supabase_client import get_admin_supabase_client

ROOT = Path(os.environ.get('PAPERPILOT_GRAPH_DIR', str(Path(__file__).resolve().parent.parent / 'graph_data')))
logger = logging.getLogger(__name__)

def _path(user_id, paper_id):
    return ROOT / str(UUID(str(user_id))) / (str(UUID(str(paper_id))) + '_status.json')

def write_progress(user_id, paper_id, stage, **details):
    # Diagnostic writes must never turn a successful ingestion into a failure.
    try:
        path = _path(user_id, paper_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(stage=stage, updated_at=datetime.now(timezone.utc).isoformat(), **details)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(tmp, path)
    except Exception:
        logger.exception('Could not save ingestion progress')

def explain_error(error):
    value = str(error or '').lower()
    known = {
        'rate_limit': '429 rate limit',
        'unreadable_pdf': 'no text chunks',
        'service_unavailable': 'connection',
        'provider_configuration': 'credentials',
    }
    value = known.get(value, value)
    if '429' in value or 'rate limit' in value or 'rate_limit' in value:
        return 'rate_limit', 'The AI provider reached its request limit. Processing can resume when capacity is available.'
    if any(x in value for x in ('no text chunks', 'empty document', 'cannot open broken document', 'encrypted', 'password')):
        return 'unreadable_pdf', 'Text could not be read from this PDF. Try an unlocked PDF with selectable text.'
    if any(x in value for x in ('timeout', 'timed out', 'connection', 'getaddrinfo', 'connecterror')):
        return 'service_unavailable', 'A processing service could not be reached. Your uploaded PDF is still saved.'
    if any(x in value for x in ('401', '403', 'api key', 'credentials', 'unauthorized')):
        return 'provider_configuration', 'A processing service rejected authorization. The app operator needs to check its configuration.'
    return 'processing_error', 'Paper processing encountered an error. Your PDF is still saved; retry processing or contact the app operator.'

def get_processing_status(paper, user_id):
    # Caller MUST first obtain paper through the authenticated ownership query.
    paper_id = paper['paper_id']
    response = (get_admin_supabase_client().table('ingestion_jobs')
        .select('status,error_message,attempts,updated_at')
        .eq('paper_id', paper_id).eq('user_id', user_id)
        .order('created_at', desc=True).limit(1).execute())
    job = (response.data or [{}])[0]
    result = dict(paper_id=paper_id, status=paper['status'], job_status=job.get('status'),
                  attempts=job.get('attempts', 0), checked_at=datetime.now(timezone.utc).isoformat())
    if paper['status'] == 'ready':
        return dict(result, stage='ready', message='Your paper is ready for questions.')
    progress = {}
    try:
        progress = json.loads(_path(user_id, paper_id).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        pass
    stage = progress.get('stage', 'queued' if job.get('status') == 'queued' else 'processing')
    messages = {'download':'Downloading your uploaded PDF.', 'extract':'Reading text from your PDF.',
        'embed':'Preparing searchable text.', 'graph':'Extracting relationships from the paper.',
        'finalize':'Saving the completed paper.', 'queued':'Waiting for a processing worker.',
        'processing':'Preparing your paper.'}
    result.update(stage=stage, message=messages.get(stage, 'Preparing your paper.'))
    for key in ('completed_chunks', 'total_chunks', 'updated_at'):
        if key in progress:
            result[key] = progress[key]
    error = job.get('error_message') or progress.get('error_code')
    if error:
        code, message = explain_error(error)
        result.update(error_code=code, message=message)
        if job.get('status') == 'queued':
            result['message'] += ' An automatic retry is queued.'
    if paper['status'] == 'failed':
        result['stage'] = 'failed'
        if not error:
            result.update(error_code='processing_error', message=explain_error('')[1])
    stamp = progress.get('updated_at') or job.get('updated_at')
    if paper['status'] == 'processing' and stamp:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds()
            if age > 180:
                result['delayed'] = True
                result['message'] += ' No recent progress was recorded. Processing may be delayed; check again shortly.'
        except (ValueError, TypeError):
            pass
    return result
