"""Benchmark & Continuous Evaluation API Endpoints."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ConsensusRecord, DocumentRecord, GroundTruthRecord, ModelRunRecord
from backend.app.db.session import get_db
from backend.app.schemas.benchmark import BenchmarkSummaryResponse, DocumentDiffResponse
from backend.app.services.evaluator import evaluator

router = APIRouter(prefix="/benchmarks", tags=["Continuous Benchmarks & Evaluation"])


@router.get(
    "/summary",
    response_model=BenchmarkSummaryResponse,
    summary="Get aggregated multi-model benchmark metrics and ECE calibration",
)
async def get_benchmark_summary(db: AsyncSession = Depends(get_db)):
    """Computes real-time accuracy, CER, and ECE across all verified documents vs ensemble."""
    # 1. Total counts
    total_docs_res = await db.execute(select(func.count(DocumentRecord.id)))
    total_docs = total_docs_res.scalar() or 0

    needs_review_res = await db.execute(
        select(func.count(DocumentRecord.id)).where(DocumentRecord.status == "NEEDS_REVIEW")
    )
    needs_review_count = needs_review_res.scalar() or 0

    # 2. Get all verified ground truth records
    gt_query = await db.execute(select(GroundTruthRecord))
    gt_records = gt_query.scalars().all()

    verified_evals: list[dict[str, Any]] = []

    for gt in gt_records:
        doc_id = gt.document_id
        gt_data = json.loads(gt.ground_truth_json)

        # Fetch consensus
        cons_res = await db.execute(
            select(ConsensusRecord).where(ConsensusRecord.document_id == doc_id)
        )
        cons_rec = cons_res.scalars().first()
        cons_data = json.loads(cons_rec.reconciled_json) if cons_rec else {}

        # Fetch raw model runs
        runs_res = await db.execute(
            select(ModelRunRecord).where(ModelRunRecord.document_id == doc_id)
        )
        runs = runs_res.scalars().all()
        runs_dicts = [
            {
                "model_name": r.model_name,
                "model_identifier": r.model_identifier,
                "raw_response_json": r.raw_response_json,
                "latency_ms": r.latency_ms,
            }
            for r in runs
        ]

        diff = evaluator.evaluate_document_diff(
            document_id=doc_id,
            ground_truth=gt_data,
            raw_runs=runs_dicts,
            consensus_data=cons_data,
        )
        verified_evals.append({"document_id": doc_id, "diff": diff})

    summary = evaluator.aggregate_benchmark_summary(
        total_documents=total_docs,
        verified_documents=verified_evals,
        needs_review_count=needs_review_count,
    )
    return summary


@router.get(
    "/documents/{document_id}/diff",
    response_model=DocumentDiffResponse,
    summary="Get field-by-field model diff against verified ground truth for a document",
)
async def get_document_diff(document_id: str, db: AsyncSession = Depends(get_db)):
    """Field-by-field inspection comparing human ground truth against Model A, B, C, and Ensemble."""
    gt_res = await db.execute(
        select(GroundTruthRecord).where(GroundTruthRecord.document_id == document_id)
    )
    gt_rec = gt_res.scalars().first()
    if not gt_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verified ground truth found for document {document_id}",
        )

    gt_data = json.loads(gt_rec.ground_truth_json)

    cons_res = await db.execute(
        select(ConsensusRecord).where(ConsensusRecord.document_id == document_id)
    )
    cons_rec = cons_res.scalars().first()
    cons_data = json.loads(cons_rec.reconciled_json) if cons_rec else {}

    runs_res = await db.execute(
        select(ModelRunRecord).where(ModelRunRecord.document_id == document_id)
    )
    runs = runs_res.scalars().all()
    runs_dicts = [
        {
            "model_name": r.model_name,
            "model_identifier": r.model_identifier,
            "raw_response_json": r.raw_response_json,
            "latency_ms": r.latency_ms,
        }
        for r in runs
    ]

    return evaluator.evaluate_document_diff(
        document_id=document_id,
        ground_truth=gt_data,
        raw_runs=runs_dicts,
        consensus_data=cons_data,
    )
