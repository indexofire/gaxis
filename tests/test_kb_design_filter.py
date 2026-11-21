"""Rejected-design figures stay extraction assets and never enter the knowledge base."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fitz")

from gaxis.config import load_config, settings
from gaxis.models.paper import DesignQuality
from gaxis.service import kb_ingest

from .manifest_factory import make_manifest


def _write(data_root: Path, manifest) -> None:
    directory = data_root / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{manifest.manifest_id.replace('/', '__')}.json").write_text(
        manifest.model_dump_json(indent=2)
    )


def _seed(data_root: Path) -> None:
    gold = make_manifest("pdf-aaaa1111/fig-1")
    gold.design = DesignQuality(
        model="vision:test",
        method="vision:test",
        aesthetic=0.8,
        visualization=0.8,
        score=0.8,
        tier="gold",
    )
    rejected = make_manifest("pdf-bbbb2222/fig-1")
    rejected.design = DesignQuality(
        model="vision:test",
        method="vision:test",
        aesthetic=0.2,
        visualization=0.2,
        score=0.2,
        tier="reject",
    )
    _write(data_root, gold)
    _write(data_root, rejected)


def test_reject_tier_is_not_indexed(fake_kb: Path, tmp_path: Path) -> None:
    data_root = settings().data_root
    _seed(data_root)
    summary = kb_ingest()
    assert summary.ok
    assert summary.upserted == ["pdf-aaaa1111/fig-1"]


def test_re_judged_figure_is_removed_from_the_index(
    fake_kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "gaxis.toml"
    config.write_text("[knowledge]\ninclude_rejected_design = true\n")
    monkeypatch.setenv("GAXIS_CONFIG", str(config))
    data_root = settings().data_root
    _seed(data_root)
    assert set(kb_ingest().upserted) == {"pdf-aaaa1111/fig-1", "pdf-bbbb2222/fig-1"}

    monkeypatch.setenv("GAXIS_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.delenv("GAXIS_CONFIG", raising=False)
    summary = kb_ingest()
    assert summary.removed == ["pdf-bbbb2222/fig-1"]


def test_include_rejected_design_indexes_everything(
    fake_kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "gaxis.toml"
    config.write_text("[knowledge]\ninclude_rejected_design = true\n")
    monkeypatch.setenv("GAXIS_CONFIG", str(config))
    data_root = settings().data_root
    _seed(data_root)
    summary = kb_ingest()
    assert set(summary.upserted) == {"pdf-aaaa1111/fig-1", "pdf-bbbb2222/fig-1"}
    assert load_config(config).knowledge.include_rejected_design is True
