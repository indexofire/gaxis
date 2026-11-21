"""LLM-assisted reconstruction: generate -> run -> compare -> revise, with provenance."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gaxis.acquire.paper import load_manifest, manifest_filename
from gaxis.models.paper import CodeCandidate
from gaxis.models.spec import ChartType
from gaxis.repro.reconstruct import _extract_code
from gaxis.service import reconstruct_chart

from .manifest_factory import make_manifest

DEMO_SCRIPT = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(4, 2.4), dpi=200)
ax.bar(['WT', 'dpsA', 'rpoS', 'hfq'], [120, 85, 150, 95], color='#009E73')
ax.set_ylabel('expr fpkm')
ax.set_xlabel('genotype')
fig.savefig('figure.png', bbox_inches='tight')
"""

BROKEN_SCRIPT = "raise RuntimeError('author environment is gone')\n"


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, with_code: bool = False):
    root = tmp_path / "data"
    monkeypatch.setenv("GAXIS_DATA_DIR", str(root))
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")
    manifests = root / "manifests"
    manifests.mkdir(parents=True)
    image = root / "assets" / "pdf-xyz" / "figures" / "fig-1.png"
    image.parent.mkdir(parents=True)
    shutil.copyfile(Path("examples/demo/figure-source.png"), image)
    manifest = make_manifest("pdf-xyz/fig-1", level="none", chart_type=ChartType.bar)
    manifest.chart_file = "assets/pdf-xyz/figures/fig-1.png"
    manifest.paper_id = "pdf-xyz"
    if with_code:
        script = tmp_path / "author_figure.py"
        script.write_text(BROKEN_SCRIPT, encoding="utf-8")
        manifest.code_candidates = [
            CodeCandidate(code_path=str(script), pairing_confidence=0.9, license="MIT")
        ]
    (manifests / manifest_filename(manifest.manifest_id)).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest


def _endpoint(*args, **kwargs):
    return ("http://127.0.0.1:9/v1", "fake-vision", "NO_KEY_NEEDED", 768, 30.0, 0.0)


def test_reconstruction_runs_and_records_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _setup(tmp_path, monkeypatch)
    calls: list[dict] = []

    def fake_request(**kwargs):
        calls.append(kwargs)
        return DEMO_SCRIPT

    monkeypatch.setattr("gaxis.repro.reconstruct._endpoint", _endpoint)
    monkeypatch.setattr("gaxis.repro.reconstruct._request_code", fake_request)
    result = reconstruct_chart(manifest.manifest_id, engine="local", rounds=2)
    assert result.method == "llm_reconstruction"
    assert result.model == "fake-vision"
    assert result.level in {"L1", "L2"}, result.failure_reason
    assert result.visual_similarity is not None
    assert Path(result.code_path).is_file()
    assert result.similarity_history
    attempt_file = Path(tmp_path / "data" / "recon" / "pdf-xyz__fig-1" / "round-1" / "attempt.json")
    assert attempt_file.is_file()
    stored = load_manifest(manifest.manifest_id, Path(tmp_path / "data" / "manifests"))
    assert stored is not None
    assert stored.reproduction.method == "llm_reconstruction"
    assert stored.reproduction.attempts == 1
    candidate = stored.code_candidates[-1]
    assert candidate.generated is True
    assert candidate.code_path == result.code_path
    assert calls
    assert calls[0]["caption"] == manifest.caption


def test_repair_starts_from_author_code_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _setup(tmp_path, monkeypatch, with_code=True)
    rounds: list[dict] = []

    def fake_request(**kwargs):
        rounds.append(kwargs)
        return DEMO_SCRIPT

    monkeypatch.setattr("gaxis.repro.reconstruct._endpoint", _endpoint)
    monkeypatch.setattr("gaxis.repro.reconstruct._request_code", fake_request)
    result = reconstruct_chart(manifest.manifest_id, engine="local", rounds=2, repair=True)
    assert result.method == "llm_repair"
    assert result.level in {"L1", "L2", "L3"}
    assert result.rounds == 2
    stored = load_manifest(manifest.manifest_id, Path(tmp_path / "data" / "manifests"))
    assert stored is not None
    assert stored.reproduction.method == "llm_repair"


def test_extract_code_requires_savefig() -> None:
    from gaxis.errors import GaxisError

    with pytest.raises(GaxisError) as excinfo:
        _extract_code("```python\nprint('hi')\n```")
    assert excinfo.value.code == "reconstruct_failed"


def test_repair_keeps_author_method_when_script_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    monkeypatch.setenv("GAXIS_DATA_DIR", str(root))
    monkeypatch.setenv("GAXIS_KB_ENABLED", "false")
    manifests = root / "manifests"
    manifests.mkdir(parents=True)
    image = root / "assets" / "pdf-xyz" / "figures" / "fig-1.png"
    image.parent.mkdir(parents=True)
    shutil.copyfile(Path("examples/demo/figure-source.png"), image)
    script = tmp_path / "author_figure.py"
    script.write_text(DEMO_SCRIPT, encoding="utf-8")
    manifest = make_manifest("pdf-xyz/fig-2", level="L2", chart_type=ChartType.bar)
    manifest.chart_file = "assets/pdf-xyz/figures/fig-1.png"
    manifest.code_candidates = [CodeCandidate(code_path=str(script), pairing_confidence=0.9)]
    (manifests / manifest_filename(manifest.manifest_id)).write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    monkeypatch.setattr("gaxis.repro.reconstruct._endpoint", _endpoint)
    monkeypatch.setattr("gaxis.repro.reconstruct._request_code", lambda **kwargs: DEMO_SCRIPT)
    result = reconstruct_chart(manifest.manifest_id, engine="local", rounds=2, repair=True)
    assert result.method == "author_code"
    stored = load_manifest(manifest.manifest_id, root / "manifests")
    assert stored is not None
    assert stored.reproduction.method == "author_code"
    assert stored.reproduction.model is None
    assert not any(candidate.generated for candidate in stored.code_candidates)


def test_normalise_code_repairs_common_imports() -> None:
    from gaxis.repro.reconstruct import _normalise_code

    fixed = _normalise_code("plt.use('Agg')\nimport matplotlib.pyplot as plt\nsavefig('x.png')\n")
    assert fixed.startswith("import matplotlib\n")
    assert "matplotlib.use(" in fixed
    assert "plt.use(" not in fixed
