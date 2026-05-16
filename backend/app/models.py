from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
import datetime

Base = declarative_base()

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    status = Column(String, default="OFFLINE")

class SuspiciousMoment(Base):
    __tablename__ = "suspicious_moments"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    event_type = Column(String, nullable=False)
    confidence = Column(Float, default=0.0)
    thumbnail_path = Column(String)
    video_path = Column(String)
    meta = Column(JSON)
    camera = relationship("Camera")

class TrackedObject(Base):
    __tablename__ = "tracked_objects"
    id = Column(Integer, primary_key=True)
    moment_id = Column(Integer, ForeignKey("suspicious_moments.id"))
    label = Column(String)
    bbox = Column(JSON)
    confidence = Column(Float)
