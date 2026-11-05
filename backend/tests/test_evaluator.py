"""Tests for Continuous Evaluation Engine & Benchmark APIs."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ConsensusRecord, DocumentRecord, GroundTruthRecord, ModelRunRecord
from backend.app.services.evaluator import (
    are_values_equivalent,
    compute_ece,
    compute_string_cer,
    evaluator,
)


def test_compute_string_cer():
    # Exact match: 0% CER
    assert compute_string_cer("Shree Ganesh", "Shree Ganesh") == 0.0

    # 1 edit in 10 characters = 0.1 (10% CER)
    assert compute_string_cer("Paracetamol", "Paracetaml") <= 0.15

    # Completely different string
    assert compute_string_cer("Invoice", "Prescription") >= 0.80

    # Empty strings
    assert compute_string_cer("", "") == 0.0


def test_are_values_equivalent():
    # Float tolerance within 0.05
    is_match, cer = are_values_equivalent(1450.00, 1450.02)
    assert is_match is True
    assert cer == 0.0

    # Float mismatch
    is_match, cer = are_values_equivalent(1450.00, 1500.00)
    assert is_match is False
    assert cer > 0.0

    # String equivalence
    is_match, cer = are_values_equivalent("Shree Ganesh Stores", "shree  ganesh stores")
    assert is_match is True
    assert cer <= 0.08

    # None handling
    assert are_values_equivalent(None, None)[0] is True
    assert are_values_equivalent("Test", None)[0] is False


def test_compute_ece():
    confs = [0.95, 0.90, 0.85, 0.60, 0.40]
    accs = [True, True, True, False, False]

    ece, buckets = compute_ece(confs, accs, num_bins=4)
    assert 0.0 <= ece <= 1.0
    assert len(buckets) > 0
    assert buckets[-1].sample_count > 0


def test_evaluate_document_diff():
    gt = {
        "fields": {
            "vendor_name": "Shree Ganesh Stores",
            "grand_total": 1400.0,
        },
        "line_items": [],
    }
    raw_runs = [
        {
            "model_name": "gemini_vlm",
            "model_identifier": "gemini-2.0",
            "raw_response_json": json.dumps(
                {"vendor_name": "Shree Ganesh Stores", "grand_total": 1400.0}
            ),
            "latency_ms": 1500.0,
        },
        {
            "model_name": "qwen_vl",
            "model_identifier": "qwen-2.5",
            "raw_response_json": json.dumps(
                {"vendor_name": "Shree Ganesh Stores", "grand_total": 1350.0}
            ),
            "latency_ms": 1800.0,
        },
    ]
    consensus = {
        "fields": {
            "vendor_name": {"value": "Shree Ganesh Stores", "confidence": 0.98},
            "grand_total": {"value": 1400.0, "confidence": 0.98},
        }
    }

    diff = evaluator.evaluate_document_diff("doc-test", gt, raw_runs, consensus)
    assert diff.document_id == "doc-test"
    assert len(diff.field_diffs) == 2
    assert diff.per_model_accuracy["ensemble"] == 100.0
    assert diff.per_model_accuracy["gemini_vlm"] == 100.0
    assert diff.per_model_accuracy["qwen_vl"] == 50.0  # 1 of 2 correct


@pytest.mark.asyncio
async def test_benchmark_summary_api(client: AsyncClient, db_session: AsyncSession):
    # Seed a verified document into DB
    doc_id = "bench-test-doc-1"
    doc = DocumentRecord(
        id=doc_id,
        filename="invoice.png",
        content_type="image/png",
        document_type="INVOICE",
        overall_confidence=0.98,
        math_valid=True,
        status="VERIFIED",
    )
    db_session.add(doc)

    gt_data = {"fields": {"vendor_name": "Acme Corp", "grand_total": 500.0}}
    gt = GroundTruthRecord(
        document_id=doc_id,
        ground_truth_json=json.dumps(gt_data),
        verified_by="evaluator-test",
    )
    db_session.add(gt)

    cons_data = {
        "fields": {
            "vendor_name": {"value": "Acme Corp", "confidence": 0.98},
            "grand_total": {"value": 500.0, "confidence": 0.98},
        }
    }
    cons = ConsensusRecord(
        document_id=doc_id,
        reconciled_json=json.dumps(cons_data),
        math_validation_json=json.dumps({"is_valid": True}),
    )
    db_session.add(cons)

    run = ModelRunRecord(
        document_id=doc_id,
        model_name="gemini_vlm",
        model_identifier="gemini-2.0",
        raw_response_json=json.dumps({"vendor_name": "Acme Corp", "grand_total": 500.0}),
        latency_ms=1200.0,
        status="SUCCESS",
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.get("/api/v1/benchmarks/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_documents_processed"] >= 1
    assert data["verified_ground_truths_count"] >= 1
    assert len(data["models"]) >= 1

    # Test document diff endpoint
    diff_resp = await client.get(f"/api/v1/benchmarks/documents/{doc_id}/diff")
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["document_id"] == doc_id
    assert len(diff_data["field_diffs"]) == 2
