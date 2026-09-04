"""Minimal tests for sensor helpers that do not need Home Assistant."""

from __future__ import annotations

from pathlib import Path


def test_sensor_module_exists() -> None:
    """Ensure the sensor platform file is present for packaging checks."""
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "cursor_usage"
        / "sensor.py"
    )
    assert path.is_file()
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "CursorModelSpendSensor" not in source
    assert "model_costs" in source
    assert "model_tokens" in source
    assert "tokens_used" in source
    assert "cursor_models_projected" in source
    assert "total_projected" in source
    assert "ATTR_MODELS" in source
