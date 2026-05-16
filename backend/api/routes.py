from fastapi import APIRouter, UploadFile, File, BackgroundTasks, WebSocket, HTTPException
from backend.pipelines.pipeline import CCTVPipeline
from backend.reports.generator import generate_report, report_markdown
from backend.config import CONFIG
from backend.utils.logger import get_logger
import asyncio
import os
import sys
import subprocess
import time

router = APIRouter()
logger = get_logger("api")

_pipeline_tasks = {}

@router.post('/upload')
async def upload_video(file: UploadFile = File(...)):
    dest = f"./uploads/{file.filename}"
    import os
    os.makedirs('./uploads', exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(await file.read())
    return {"path": dest}



@router.get('/videos')
def list_videos():
    vdir = os.path.join('.', 'videos')
    if not os.path.isdir(vdir):
        return {'videos': []}
    files = [f for f in os.listdir(vdir) if os.path.isfile(os.path.join(vdir, f))]
    return {'videos': sorted(files)}


@router.post('/replay')
def make_replay():
    """Run the local replay generator script to create a replay for the latest event.
    Returns the path of the generated replay if available.
    """
    script = os.path.join('.', 'scripts', 'show_latest_event.py')
    if not os.path.exists(script):
        raise HTTPException(status_code=500, detail='replay script not found')

    # run script synchronously and wait briefly for output file
    try:
        subprocess.check_call([sys.executable, script])
    except Exception:
        # try running without opening (script is quiet) but ignore errors
        pass

    # look for the most recent replay file
    rdir = os.path.join('.', 'storage', 'clips', 'replay')
    if not os.path.isdir(rdir):
        raise HTTPException(status_code=404, detail='no replay directory')
    files = [os.path.join(rdir, f) for f in os.listdir(rdir) if f.endswith('.mp4')]
    if not files:
        raise HTTPException(status_code=404, detail='no replay files')
    latest = max(files, key=os.path.getmtime)
    # Return a URL path under /storage so the UI can open it
    rel = os.path.relpath(latest, start=os.path.join('.', 'storage'))
    url_path = '/storage/' + rel.replace(os.sep, '/')
    return {'replay': url_path}

@router.post('/analyze')
async def analyze_stream(source: str):
    # start pipeline in background
    loop = asyncio.get_event_loop()
    pipe = CCTVPipeline(source)
    task = loop.create_task(pipe.run())
    _pipeline_tasks[source] = task
    return {"status": "started", "source": source}

@router.get('/events')
async def get_events(limit: int = 100):
    return generate_report(limit=limit)

@router.websocket('/ws/alerts')
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    # simple demo: stream DB events periodically
    import time
    while True:
        rep = generate_report(limit=10)
        await ws.send_json(rep['summary'])
        await asyncio.sleep(5)
