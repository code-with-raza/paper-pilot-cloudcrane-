"""Prepare retrieval once without blocking API health or first questions."""
import importlib
import logging
import threading
import time

_lock = threading.Lock()
_state = {'state': 'not_started'}
_request_lock = threading.BoundedSemaphore(1)
logger = logging.getLogger(__name__)

def _load():
    started = time.monotonic()
    try:
        importlib.import_module('Graph_Rag.answer_generator')
        with _lock:
            _state.update(state='ready', load_seconds=round(time.monotonic()-started, 2))
        logger.info('Question engine ready in %.2fs', time.monotonic()-started)
    except Exception:
        logger.exception('Question engine initialization failed')
        with _lock:
            _state.update(state='unavailable')

def start():
    with _lock:
        if _state['state'] in ('warming', 'ready'):
            return
        _state.update(state='warming')
    threading.Thread(target=_load, name='paperpilot-question-warmup', daemon=True).start()

def status():
    with _lock:
        return dict(_state)

def request_slot():
    return _request_lock

def public_failure(error):
    """Classify chained errors without exposing provider bodies or keys."""
    chain=[]
    seen=set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        chain.append(str(error).lower()+' '+type(error).__name__.lower())
        error=error.__cause__ or error.__context__
    text=' '.join(chain)
    if 'no searchable text' in text:
        return 503, 'The saved search index for this paper is unavailable. The app operator needs to restore or reprocess its index; your PDF is still saved.'
    if any(x in text for x in ('429', 'ratelimit', 'rate limit')):
        return 429, 'The AI provider is temporarily rate limited. Your question is kept. Wait a moment, then tap Ask again.'
    if any(x in text for x in ('timeout', 'timed out')):
        return 504, 'The answer service took too long to respond. Your question is kept. Tap Ask to retry.'
    if any(x in text for x in ('connecterror', 'connection', 'getaddrinfo', 'chroma server')):
        return 503, 'A search or answer service is unavailable. Your question is kept. Please try again shortly.'
    return 500, 'The answer could not be completed. Your question is kept. Tap Ask to retry.'
