"""Run one private Chroma, API and ingestion worker in a volume-backed service."""
import gzip
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path('/app')
DATA=Path(os.environ.get('PAPERPILOT_DATA_DIR','/data'))
processes=[]
stopping=False

def launch(name,args):
    print('Starting '+name,flush=True)
    process=subprocess.Popen(args,cwd=ROOT)
    processes.append((name,process))
    return process

def stop(*_):
    global stopping
    if stopping:return
    stopping=True
    for _,process in reversed(processes):
        if process.poll() is None:process.terminate()
    for _,process in reversed(processes):
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill()

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    graphs=DATA/'graphs';graphs.mkdir(exist_ok=True)
    # Both API and worker use the same persistent graph/status directory.
    os.environ['PAPERPILOT_GRAPH_DIR']=str(graphs)
    for key in ('SUPABASE_URL','SUPABASE_KEY','SUPABASE_SERVICE_ROLE_KEY','GROQ_API_KEY','OPENROUTER_API_KEY'):
        if not os.environ.get(key):raise RuntimeError('Required runtime secret is missing: '+key)
    chroma=launch('private Chroma',['chroma','run','--host','127.0.0.1','--port','8001','--path',str(DATA/'chroma')])
    for _ in range(90):
        if chroma.poll() is not None:raise RuntimeError('Chroma exited before readiness')
        try:
            urllib.request.urlopen('http://127.0.0.1:8001/api/v2/heartbeat',timeout=2).read();break
        except Exception:time.sleep(1)
    else:raise RuntimeError('Chroma readiness timed out')
    seed=ROOT/'seed/bootstrap.json.gz'
    marker=DATA/'.bootstrap-complete'
    if seed.exists() and not marker.exists():
        import chromadb
        payload=json.loads(gzip.decompress(seed.read_bytes()))
        client=chromadb.HttpClient(host='127.0.0.1',port=8001)
        for name,rows in payload.get('collections',{}).items():
            collection=client.get_or_create_collection(name)
            if rows['ids']:
                collection.upsert(ids=rows['ids'],documents=rows['documents'],metadatas=rows['metadatas'],embeddings=rows['embeddings'])
            print('Restored collection records:',name,len(rows['ids']),flush=True)
        for relative,content in payload.get('graphs',{}).items():
            dest=(graphs/relative).resolve()
            if not dest.is_relative_to(graphs.resolve()):raise RuntimeError('Unsafe seed graph path')
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.write_text(content,encoding='utf-8')
        marker.write_text('complete',encoding='ascii')
    launch('API',[sys.executable,'-u','-m','uvicorn','deploy_app:app','--host','0.0.0.0','--port',os.environ.get('PORT','8000'),'--timeout-graceful-shutdown','10'])
    # deploy_app runs ingestion in the API process, sharing its cached model.
    while not stopping:
        for name,process in processes:
            if process.poll() is not None:
                memory_events=Path('/sys/fs/cgroup/memory.events')
                diagnostics=memory_events.read_text() if memory_events.exists() else 'unavailable'
                raise RuntimeError(f'{name} exited with code {process.returncode}; cgroup memory events: {diagnostics}')
        time.sleep(2)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:main()
    finally:stop()
