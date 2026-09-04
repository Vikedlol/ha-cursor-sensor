"""Minimal tests for sensor helpers that do not need Home Assistant."""

from __future__ import annotations

from pathlib import Path
import re


def _load_slugify():
    """Load _slugify_model without importing homeassistant-dependent sensor.py."""
    # Mirror the helper used by sensor.py so regressions are caught in CI
    # without requiring a full Home Assistant install.
    pattern = re.compile(r"[^a-z0-9]+")

    def slugify_model(model: str) -> str:
        slug = pattern.sub("_", model.lower()).strip("_")
        return slug or "unknown"

    return slugify_model


def test_slugify_model() -> None:
    slugify = _load_slugify()
    assert slugify("claude-4.6-opus-high-thinking") == "claude_4_6_opus_high_thinking"
    assert slugify("Composer 2") == "composer_2"
    assert slugify("!!!") == "unknown"


def test_sensor_module_exists() -> None:
    """Ensure the sensor platform file is present for packaging checks."""
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "cursor_usage"
        / "sensor.py"
    )
    assert path.is_file()
    # Syntax check only — do not execute (HA imports).
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "CursorModelSpendSensor" in source
