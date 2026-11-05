"""Benchmark & Continuous Evaluation Schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ModelEvaluationMetric(BaseModel):
    """Aggregated evaluation metrics for a single model or ensemble."""

    model_name: str
    exact_match_accuracy: float = Field(..., description="Exact match percentage (0.0 - 100.0)")
    cer: float = Field(..., description="Character Error Rate percentage (0.0 - 100.0)")
    total_fields_evaluated: int = 0
    correct_fields_count: int = 0
    avg_latency_ms: float = 0.0
    math_error_intercept_rate: float = 100.0


class ECEBucket(BaseModel):
    """Reliability diagram bin for Expected Calibration Error."""

    confidence_bin: str
    avg_confidence: float
    accuracy: float
    sample_count: int


class BenchmarkSummaryResponse(BaseModel):
    """System-wide continuous evaluation benchmark summary."""

    total_documents_processed: int
    verified_ground_truths_count: int
    needs_review_count: int
    models: list[ModelEvaluationMetric]
    ensemble_accuracy_gain: float = Field(
        default=0.0, description="Ensemble accuracy minus highest individual model accuracy"
    )
    expected_calibration_error: float = Field(
        default=0.0, description="ECE across all calibrated fields"
    )
    calibration_curve: list[ECEBucket] = Field(default_factory=list)


class FieldDiff(BaseModel):
    """Detailed diff for a single field against ground truth."""

    field_name: str
    ground_truth_value: Any
    ensemble_value: Any
    ensemble_correct: bool
    model_predictions: dict[str, dict[str, Any]]  # model_name -> {value, correct, cer}


class DocumentDiffResponse(BaseModel):
    """Document-level diff comparing all models against verified ground truth."""

    document_id: str
    field_diffs: list[FieldDiff] = Field(default_factory=list)
    line_item_count: int = 0
    per_model_accuracy: dict[str, float] = Field(default_factory=dict)
