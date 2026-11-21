"""Vision judge: payload preparation, tolerant parsing, local endpoint without a key."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from gaxis.design_judge import (
    DesignJudgeError,
    HeuristicJudge,
    VisionJudge,
    parse_judgement,
)


def _image(tmp_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = tmp_path / "figure.png"
    figure, axis = plt.subplots(figsize=(6, 4), dpi=300)
    axis.bar(["A", "B"], [1, 2])
    figure.savefig(path, facecolor="white")
    plt.close(figure)
    return path


def test_payload_downscales_and_encodes_jpeg(tmp_path: Path) -> None:
    import base64
    import io

    from PIL import Image

    judge = VisionJudge(base_url="http://127.0.0.1:11434/v1", model="local-vl", max_side=256)
    payload = judge._payload(_image(tmp_path), "caption")
    data_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    encoded = data_url.split("base64,", 1)[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as sent:
        assert max(sent.size) <= 256
        assert sent.format == "JPEG"


def test_judgement_parsing_tolerates_fences_and_prose() -> None:
    payload = parse_judgement(
        'Sure!\n```json\n{"aesthetic": 8, "visualization": 7.5, '
        '"rationale": ["clean palette", "units present"]}\n```'
    )
    assert payload["aesthetic"] == 8.0
    assert payload["visualization"] == 7.5
    assert payload["rationale"][0] == "clean palette"


def test_judgement_parsing_rejects_garbage() -> None:
    with pytest.raises(DesignJudgeError):
        parse_judgement("no json here")


def test_local_endpoint_does_not_require_a_key() -> None:
    judge = VisionJudge(base_url="http://127.0.0.1:11434/v1", model="local-vl", api_key_env="NOPE")
    assert judge.api_key == ""
    # a remote endpoint without a key must fail loudly instead of sending nothing
    remote = VisionJudge(base_url="https://api.example.com/v1", model="m", api_key_env="NOPE")
    with pytest.raises(DesignJudgeError, match="API key"):
        remote.judge(b"", caption="")


def test_heuristic_judge_leaves_aesthetics_unjudged(tmp_path: Path) -> None:
    quality = HeuristicJudge().judge(_image(tmp_path), caption="Fig 1 | bars, n = 3, error bars")
    assert quality.aesthetic is None
    assert quality.method == "objective"
    assert quality.visualization > 0.5


def test_build_judge_accepts_a_local_vision_endpoint(tmp_path, monkeypatch) -> None:
    from gaxis.config import load_config
    from gaxis.design_judge import build_judge

    config = tmp_path / "gaxis.toml"
    config.write_text(
        "[design]\njudge = 'vision'\nbase_url = 'http://127.0.0.1:11434/v1'\n"
        "model = 'qwen2.5vl:7b'\napi_key_env = 'NOPE'\n"
    )
    monkeypatch.delenv("NOPE", raising=False)
    judge = build_judge(type("S", (), {"config": load_config(config)})())
    assert judge.name == "vision:qwen2.5vl:7b"

    remote = tmp_path / "remote.toml"
    remote.write_text(
        "[design]\njudge = 'vision'\nbase_url = 'https://api.example.com/v1'\n"
        "model = 'm'\napi_key_env = 'NOPE'\n"
    )
    fallback = build_judge(type("S", (), {"config": load_config(remote)})())
    assert fallback.name == "heuristic"
