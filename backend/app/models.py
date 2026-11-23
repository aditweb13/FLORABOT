from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now_utc():
    return datetime.now(timezone.utc)

class Plant(Base):
    __tablename__ = "plants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    species: Mapped[str] = mapped_column(String(160), default="Unknown")
    category: Mapped[str] = mapped_column(String(80), default="Houseplant")
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    location: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    health_status: Mapped[str] = mapped_column(String(40), default="Unscanned")
    pot_size_cm: Mapped[int] = mapped_column(Integer, default=15)
    soil_type: Mapped[str] = mapped_column(String(80), default="Potting Mix")
    watering_frequency_days: Mapped[int] = mapped_column(Integer, default=7)
    
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="plant", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="plant", cascade="all, delete-orphan")
    camera_images: Mapped[list["CameraImage"]] = relationship(back_populates="plant")

class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    identifier: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="ESP32-CAM Sensor")
    type: Mapped[str] = mapped_column(String(60), default="ESP32-CAM")
    status: Mapped[str] = mapped_column(String(30), default="offline")  # online, offline, stale
    ip_address: Mapped[str] = mapped_column(String(60), default="")
    stream_url: Mapped[str] = mapped_column(String(250), default="")
    snapshot_url: Mapped[str] = mapped_column(String(250), default="")
    last_communication: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_image_received: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    
    images: Mapped[list["CameraImage"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="device")
    logs: Mapped[list["DeviceLog"]] = relationship(back_populates="device", cascade="all, delete-orphan")

class DeviceLog(Base):
    __tablename__ = "device_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # connected, heartbeat, image_received, analysis_complete, error
    message: Mapped[str] = mapped_column(String(300))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    
    device: Mapped[Device] = relationship(back_populates="logs")

class CameraImage(Base):
    __tablename__ = "camera_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"), nullable=True, index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    processing_status: Mapped[str] = mapped_column(String(40), default="received")  # received, validating, analyzing, completed, failed
    error_message: Mapped[str] = mapped_column(String(300), default="")
    
    device: Mapped[Device | None] = relationship(back_populates="images")
    plant: Mapped[Plant | None] = relationship(back_populates="camera_images")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="camera_image")

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("camera_images.id"), nullable=True, index=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    image: Mapped[str] = mapped_column(String(500))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    
    plant_identification: Mapped[str] = mapped_column(String(160), default="Unknown")
    plant_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    disease_detected: Mapped[str] = mapped_column(String(30), default="uncertain")  # yes, no, uncertain
    disease_name: Mapped[str] = mapped_column(String(180), default="")
    disease_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(60), default="")
    health_status: Mapped[str] = mapped_column(String(40), default="Inconclusive")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    symptoms: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[str] = mapped_column(Text, default="")
    prevention: Mapped[str] = mapped_column(Text, default="")
    recovery_plan: Mapped[str] = mapped_column(Text, default="")
    
    # Stress & Wilting assessment
    stress_status: Mapped[str] = mapped_column(String(60), default="None")
    stress_observations: Mapped[str] = mapped_column(Text, default="")
    
    # Watering recommendation engine
    watering_status: Mapped[str] = mapped_column(String(80), default="Watering condition uncertain")
    watering_quantity_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watering_reason: Mapped[str] = mapped_column(Text, default="")
    watering_instructions: Mapped[str] = mapped_column(Text, default="")
    
    # Diagnostics provider
    provider_engine: Mapped[str] = mapped_column(String(80), default="FloraBOT Vision Engine")
    provider_reference: Mapped[str] = mapped_column(String(200), default="")
    
    plant: Mapped[Plant] = relationship(back_populates="analyses")
    device: Mapped[Device | None] = relationship(back_populates="analyses")
    camera_image: Mapped[CameraImage | None] = relationship(back_populates="analyses")
    reports: Mapped[list["Report"]] = relationship(back_populates="analysis")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    report_data_json: Mapped[str] = mapped_column(Text, default="{}")
    file_path: Mapped[str] = mapped_column(String(500))
    
    plant: Mapped[Plant] = relationship(back_populates="reports")
    analysis: Mapped[Analysis | None] = relationship(back_populates="reports")

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Plant Consultation")
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"), nullable=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system
    content: Mapped[str] = mapped_column(Text)
    context_type: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    
    conversation: Mapped[Conversation] = relationship(back_populates="messages")

class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)  # indoor_plants, diseases, watering, care_guides, symptoms
    plant_species: Mapped[str] = mapped_column(String(160), default="")
    disease_name: Mapped[str] = mapped_column(String(160), default="")
    summary: Mapped[str] = mapped_column(Text)
    details_markdown: Mapped[str] = mapped_column(Text)
    care_data_json: Mapped[str] = mapped_column(Text, default="{}")  # light, water, humidity, soil, temperature
    treatment_plan: Mapped[str] = mapped_column(Text, default="")
    prevention_tips: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(160), default="FloraBOT Botanical Reference Library")
    source_url: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
