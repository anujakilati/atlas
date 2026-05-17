from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import AsyncSessionLocal
from .. import models, schemas

router = APIRouter(prefix="/events", tags=["events"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/", response_model=list[schemas.SuspiciousMomentSchema])
async def list_events(db: AsyncSession = Depends(get_db)):
    result = await db.execute(models.Base.metadata.tables['suspicious_moments'].select().order_by(models.SuspiciousMoment.timestamp.desc()))
    rows = result.fetchall()
    return [r for r in rows]

@router.delete("/{id}")
async def delete_event(id: int, db: AsyncSession = Depends(get_db)):
    q = models.SuspiciousMoment.__table__.delete().where(models.SuspiciousMoment.id == id)
    await db.execute(q)
    await db.commit()
    return {"ok": True}
