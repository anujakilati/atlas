from fastapi import APIRouter, UploadFile, File, BackgroundTasks, WebSocket
from backend.pipelines.pipeline import CCTVPipeline
from backend.reports.generator import generate_report, report_markdown
from backend.config import CONFIG
from backend.utils.logger import get_logger
import asyncio

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
