from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import AsyncSessionLocal
from .. import models, schemas

router = APIRouter(prefix="/cameras", tags=["cameras"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/", response_model=list[schemas.CameraSchema])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(models.Base.metadata.tables['cameras'].select())
    rows = result.fetchall()
    return [r for r in rows]
