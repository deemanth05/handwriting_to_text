"""Unit tests for Runtime Discovery and Health Probing."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.services.models.runtime_probe import RuntimeProbe


@pytest.mark.asyncio
async def test_probe_ollama_online():
    probe = RuntimeProbe()
    mock_data = {
        "models": [
            {"name": "gemma3:12b"},
            {"name": "qwen2.5:7b"},
        ]
    }
    mock_resp = httpx.Response(
        status_code=200,
        json=mock_data,
        request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        report = await probe.probe_ollama()
        assert report["status"] == "ONLINE"
        assert "gemma3:12b" in report["models"]
        assert report["has_vision"] is True
        assert "gemma3:12b" in report["vision_models"]


@pytest.mark.asyncio
async def test_probe_ollama_offline():
    probe = RuntimeProbe()
    with patch.object(httpx.AsyncClient, "get", side_effect=httpx.ConnectError("Connection refused")):
        report = await probe.probe_ollama()
        assert report["status"] == "OFFLINE"
        assert report["has_vision"] is False


@pytest.mark.asyncio
async def test_probe_all_concurrent():
    probe = RuntimeProbe()
    with patch.object(httpx.AsyncClient, "get", side_effect=httpx.ConnectError("Offline")):
        full_report = await probe.probe_all()
        assert "runtimes" in full_report
        assert full_report["runtimes"]["ollama"]["status"] == "OFFLINE"
        assert full_report["runtimes"]["lmstudio"]["status"] == "OFFLINE"
        assert full_report["runtimes"]["surya_local"]["status"] in ["ONLINE", "UNAVAILABLE", "DISABLED"]
        assert full_report["runtimes"]["rapidocr_local"]["status"] == "ONLINE"
