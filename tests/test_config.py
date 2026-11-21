"""Configuration: TOML file, env overrides, and loud failures."""

from pathlib import Path

import pytest

from gaxis.config import load_config
from gaxis.errors import GaxisError


def test_defaults_are_sane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GAXIS_CONFIG", raising=False)
    for name in ("GAXIS_CONFIRM_MODE", "GAXIS_CONFIRM_MIN_CONFIDENCE", "GAXIS_INGEST_MODE"):
        monkeypatch.delenv(name, raising=False)
    config = load_config()
    assert config.confirmation.mode == "auto"
    assert config.confirmation.min_confidence == 0.6
    assert config.ingest.default_mode == "kb_first"
    assert config.knowledge.source == "paper-kb"


def test_file_values_are_used(tmp_path: Path) -> None:
    path = tmp_path / "gaxis.toml"
    path.write_text(
        """
[confirmation]
mode = "always"
min_confidence = 0.8

[ingest]
default_mode = "full"
allow_network = false
"""
    )
    config = load_config(path)
    assert config.confirmation.mode == "always"
    assert config.confirmation.min_confidence == 0.8
    assert config.ingest.default_mode == "full"
    assert config.ingest.allow_network is False


def test_environment_overrides_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "gaxis.toml"
    path.write_text("[confirmation]\nmin_confidence = 0.4\n")
    monkeypatch.setenv("GAXIS_CONFIRM_MIN_CONFIDENCE", "0.95")
    assert load_config(path).confirmation.min_confidence == 0.95


def test_invalid_toml_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("[confirmation\nmode = 'always'\n")
    with pytest.raises(GaxisError) as excinfo:
        load_config(path)
    assert excinfo.value.code == "config_invalid"


def test_out_of_range_confidence_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[confirmation]\nmin_confidence = 1.5\n")
    with pytest.raises(GaxisError) as excinfo:
        load_config(path)
    assert excinfo.value.code == "config_invalid"


def test_missing_explicit_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(GaxisError) as excinfo:
        load_config(tmp_path / "nope.toml")
    assert excinfo.value.code == "config_not_found"
