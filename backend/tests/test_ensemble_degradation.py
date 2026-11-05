"""Tests for Ensemble Dispatcher Graceful Degradation."""

import pytest

from backend.app.schemas.document import DocumentType
from backend.app.services.ensemble import EnsembleDispatcher
from backend.app.services.models.mock_extractor import MockVisionExtractor


@pytest.mark.asyncio
async def test_ensemble_all_models_succeed():
    extractors = [
        MockVisionExtractor("m1", "id1", {"vendor": "Store A"}),
        MockVisionExtractor("m2", "id2", {"vendor": "Store A"}),
        MockVisionExtractor("m3", "id3", {"vendor": "Store A"}),
    ]
    dispatcher = EnsembleDispatcher(extractors=extractors)
    res = await dispatcher.dispatch(b"fake_image_bytes", DocumentType.INVOICE)

    assert len(res.successful_runs) == 3
    assert len(res.failed_runs) == 0
    assert res.confidence_penalty == 0.0
    assert res.degraded_mode is False


@pytest.mark.asyncio
async def test_ensemble_single_model_failure_graceful_degradation():
    extractors = [
        MockVisionExtractor("m1", "id1", {"vendor": "Store A"}),
        MockVisionExtractor("m2", "id2", {"vendor": "Store A"}),
        MockVisionExtractor("m3", "id3", should_fail=True),
    ]
    dispatcher = EnsembleDispatcher(extractors=extractors)
    res = await dispatcher.dispatch(b"fake_image_bytes", DocumentType.INVOICE)

    # 1 model failed: pipeline does not crash! Gracefully continues with 2 models
    assert len(res.successful_runs) == 2
    assert len(res.failed_runs) == 1
    assert res.confidence_penalty == 0.10
    assert res.degraded_mode is True


@pytest.mark.asyncio
async def test_ensemble_model_timeout():
    extractors = [
        MockVisionExtractor("m1", "id1", {"vendor": "Store A"}),
        MockVisionExtractor("m2", "id2", should_timeout=True),
        MockVisionExtractor("m3", "id3", {"vendor": "Store A"}),
    ]
    dispatcher = EnsembleDispatcher(extractors=extractors)
    res = await dispatcher.dispatch(b"fake_image_bytes", DocumentType.INVOICE)

    assert len(res.successful_runs) == 2
    assert len(res.failed_runs) == 1
    assert res.failed_runs[0].status == "TIMEOUT"
    assert res.degraded_mode is True
