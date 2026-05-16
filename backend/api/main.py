from fastapi import FastAPI
from backend.api.routes import router
from backend.utils.logger import get_logger

logger = get_logger('main')
app = FastAPI(title='CCTV AI Analyzer')
app.include_router(router, prefix='/api')

@app.get('/')
def health():
    return {"status": "ok"}
