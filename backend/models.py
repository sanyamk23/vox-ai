from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base

_UTC = timezone.utc


def _now():
    return datetime.now(_UTC)


class CallSession(Base):
    __tablename__ = "chat_callsession"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), default="", index=True)
    candidate_name = Column(String(200), default="Candidate")
    candidate_phone = Column(String(20), default="", index=True)
    job_description = Column(Text, default="")
    resume_text = Column(Text, default="")
    transcript = Column(JSONB, default=list)
    notes = Column(JSONB, default=dict)
    summary = Column(Text, default="")
    intent_score = Column(Integer, nullable=True)
    call_outcome = Column(String(30), default="")
    call_channel = Column(String(20), default="web")
    created_at = Column(DateTime(timezone=True), default=_now)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    interview_context = Column(JSONB, default=dict)
    dimension_scores = Column(JSONB, nullable=True)
    eval_confidence = Column(Float, nullable=True)
    eval_reasoning = Column(Text, default="")
    candidate_summary = Column(JSONB, nullable=True)
    session_token = Column(String(36), default="", index=True)
    session_data = Column(JSONB, default=dict)


class Campaign(Base):
    __tablename__ = "chat_campaign"

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))
    job_description = Column(Text, default="")
    voice_id = Column(String(50), default="priya")
    delay_seconds = Column(Integer, default=30)
    status = Column(String(20), default="draft")
    total_uploaded = Column(Integer, default=0)
    valid_count = Column(Integer, default=0)
    invalid_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    candidates = relationship("CampaignCandidate", back_populates="campaign", lazy="select")


class CampaignCandidate(Base):
    __tablename__ = "chat_campaigncandidate"

    PENDING = "pending"
    CALLING = "calling"
    COMPLETED = "completed"
    FAILED = "failed"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("chat_campaign.id", ondelete="CASCADE"))
    name = Column(String(200))
    phone = Column(String(20))
    status = Column(String(20), default="pending")
    call_sid = Column(String(100), default="")
    call_duration = Column(Integer, default=0)
    call_outcome = Column(String(50), default="")
    transcript = Column(JSONB, default=list)
    notes = Column(JSONB, default=dict)
    ai_summary = Column(Text, default="")
    interest_level = Column(String(30), default="")
    is_valid = Column(Boolean, default=True)
    is_duplicate = Column(Boolean, default=False)
    validation_error = Column(String(200), default="")
    created_at = Column(DateTime(timezone=True), default=_now)
    called_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    campaign = relationship("Campaign", back_populates="candidates")
