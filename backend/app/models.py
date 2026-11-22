from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now(): return datetime.now(timezone.utc)

class Plant(Base):
    __tablename__ = "plants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    species: Mapped[str] = mapped_column(String(160), default="Unknown")
    category: Mapped[str] = mapped_column(String(80), default="Other")
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    location: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    health_status: Mapped[str] = mapped_column(String(40), default="Unscanned")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="plant", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="plant", cascade="all, delete-orphan")

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), index=True)
    image: Mapped[str] = mapped_column(String(500))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    plant_identification: Mapped[str] = mapped_column(String(160), default="Unknown")
    disease_detected: Mapped[str] = mapped_column(String(30), default="uncertain")
    disease_name: Mapped[str] = mapped_column(String(180), default="")
    severity: Mapped[str] = mapped_column(String(60), default="")
    health_status: Mapped[str] = mapped_column(String(40), default="Inconclusive")
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    symptoms: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[str] = mapped_column(Text, default="")
    prevention: Mapped[str] = mapped_column(Text, default="")
    provider_reference: Mapped[str] = mapped_column(String(200), default="")
    plant: Mapped[Plant] = relationship(back_populates="analyses")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    file_path: Mapped[str] = mapped_column(String(500))
    plant: Mapped[Plant] = relationship(back_populates="reports")

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
