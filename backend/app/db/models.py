"""SQLAlchemy 2.0 Database Models.

Stores documents, verbatim raw model responses (for benchmark reproducibility),
consensus extractions, and future HITL ground truth.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def utc_now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    """Uploaded and processed document entity."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    content_type = Column(String(64), nullable=False)
    document_type = Column(String(32), nullable=False, default="INVOICE")
    overall_confidence = Column(Float, nullable=False, default=0.0)
    math_valid = Column(Boolean, nullable=False, default=True)
    status = Column(
        String(32), nullable=False, default="PROCESSED"
    )  # PROCESSED, NEEDS_REVIEW, VERIFIED
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    model_runs = relationship(
        "ModelRunRecord", back_populates="document", cascade="all, delete-orphan"
    )
    consensus = relationship(
        "ConsensusRecord", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    ground_truth = relationship(
        "GroundTruthRecord", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )


class ModelRunRecord(Base):
    """Raw unmodified extraction output from an individual vision model."""

    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name = Column(String(64), nullable=False)
    model_identifier = Column(String(128), nullable=False)
    raw_response_text = Column(Text, nullable=True)
    raw_response_json = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0)
    status = Column(String(32), default="SUCCESS")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("DocumentRecord", back_populates="model_runs")


class ConsensusRecord(Base):
    """Reconciled ensemble output and math audit."""

    __tablename__ = "consensus_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    reconciled_json = Column(Text, nullable=False)
    math_validation_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("DocumentRecord", back_populates="consensus")


class GroundTruthRecord(Base):
    """Human-in-the-loop verified ground truth (used for continuous benchmarking)."""

    __tablename__ = "ground_truth_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ground_truth_json = Column(Text, nullable=False)
    verified_by = Column(String(128), nullable=True)
    verified_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("DocumentRecord", back_populates="ground_truth")
