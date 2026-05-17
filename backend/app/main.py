import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .db import init_db
from .api import cameras, events
from .ws import manager
from .services.detector import CameraWorker
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Atlas Suspicious Activity Detection")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(events.router)

# Serve saved clips and thumbnails from storage path
app.mount("/storage", StaticFiles(directory=settings.STORAGE_PATH), name="storage")

workers = []

@app.on_event("startup")
async def startup_event():
    await init_db()
    # camera urls can be provided in .env as comma separated
    urls = []
    if settings.CAMERA_URLS:
        urls = settings.CAMERA_URLS
    # start workers
    for idx, url in enumerate(urls):
        w = CameraWorker(camera_id=idx + 1, url=url, name=f"cam-{idx+1}")
        workers.append(w)
        asyncio.create_task(w.start())

@app.on_event("shutdown")
async def shutdown_event():
    for w in workers:
        w.stop()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
