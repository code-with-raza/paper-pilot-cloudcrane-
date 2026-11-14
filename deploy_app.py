from main import app
from fastapi import HTTPException
from api.question_engine import status
from contextlib import asynccontextmanager
import logging
import threading
import time

worker_thread = None
worker_loaded = threading.Event()


def ingestion_loop():
    # Wait for retrieval to finish importing the shared embedding module.
    # Starting both heavy imports together duplicates memory and startup work.
    while status()['state'] in ('not_started', 'warming'):
        time.sleep(0.2)
    if status()['state'] != 'ready':
        return
    try:
        from worker import run_worker
        worker_loaded.set()
        run_worker()
    except Exception:
        logging.getLogger(__name__).exception('Ingestion worker initialization failed')


original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def deployed_lifespan(application):
    global worker_thread
    async with original_lifespan(application):
        worker_thread = threading.Thread(target=ingestion_loop, name='paperpilot-ingestion', daemon=True)
        worker_thread.start()
        yield


app.router.lifespan_context = deployed_lifespan

@app.get('/ready')
def ready():
    if status()['state']!='ready':
        raise HTTPException(status_code=503,detail='Question service is preparing')
    if not worker_loaded.is_set() or worker_thread is None or not worker_thread.is_alive():
        raise HTTPException(status_code=503,detail='PDF processing service is preparing or unavailable')
    return {'status':'ready'}
