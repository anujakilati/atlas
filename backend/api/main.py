from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.api.routes import router
from backend.utils.logger import get_logger
import os

logger = get_logger('main')
app = FastAPI(title='CCTV AI Analyzer')
app.include_router(router, prefix='/api')

# Serve a tiny static UI for selecting videos and triggering analysis
static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.isdir(static_dir):
    app.mount('/ui', StaticFiles(directory=static_dir, html=True), name='ui')

# Serve storage directory so generated replay files are reachable at /storage/...
storage_dir = os.path.join(os.getcwd(), 'storage')
if os.path.isdir(storage_dir):
    app.mount('/storage', StaticFiles(directory=storage_dir), name='storage')

@app.get('/')
def health():
    return {"status": "ok"}
