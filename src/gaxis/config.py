"""Configuration: a TOML file plus environment overrides, one typed object.

Search order (first hit wins):
    1. explicit path (CLI --config)
    2. $GAXIS_CONFIG
    3. ./gaxis.toml (project)
    4. ${XDG_CONFIG_HOME:-~/.config}/gaxis/config.toml (user)

Environment overrides (always win): GAXIS_DATA_DIR, GAXIS_RENDER_TIMEOUT,
GAXIS_CONFIRM_MODE, GAXIS_CONFIRM_MIN_CONFIDENCE, GAXIS_INGEST_MODE,
GAXIS_GBRAIN_HOME.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .errors import GaxisError

ConfirmationMode = Literal["auto", "always", "never"]
IngestMode = Literal["kb_first", "full"]
Backend = Literal["python", "r"]


class ConfirmationSettings(BaseModel):
    """When a host must confirm with the user before rendering."""

    mode: ConfirmationMode = "auto"
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class RenderSettings(BaseModel):
    timeout_s: float = Field(default=180.0, gt=0, le=3600)
    default_preset: str = "default"
    default_backend: Backend = "python"


class IngestSettings(BaseModel):
    """Service flow 2 defaults: knowledge base first, deep parsing only on demand."""

    default_mode: IngestMode = "kb_first"
    allow_network: bool = True
    timeout_s: float = Field(default=900.0, gt=0, le=7200)
    min_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    contact_email: str = Field(default="", description="Unpaywall/NCBI politeness address")
    max_download_mb: float = Field(default=40.0, gt=0, le=500)
    with_code: bool = True
    repo_timeout_s: float = Field(default=120.0, gt=0, le=900)
    max_repos: int = Field(default=2, ge=0, le=10)


class DesignSettings(BaseModel):
    """How design quality is judged: offline heuristics or a vision model."""

    judge: Literal["heuristic", "vision"] = "heuristic"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_s: float = Field(default=300.0, gt=0, le=900)
    max_side: int = Field(default=768, ge=256, le=2048, description="vision input long side, px")
    gold_score: float = Field(
        default=0.60, ge=0.0, le=1.0, description="select for golden set / retrieval priority"
    )
    dense_score: float = Field(
        default=0.45, ge=0.0, le=1.0, description="usable but dense; below this is rejected"
    )
    retries: int = Field(default=2, ge=0, le=5)
    skip_plates: bool = Field(
        default=False,
        description="external montages: clear score/tier and use as style references only",
    )
    allow_nonchart: bool = Field(
        default=False, description="index schematics/micrographs as examples (rejected by default)"
    )


class ReconstructSettings(BaseModel):
    """LLM-assisted figure reconstruction: the model writes code, the sandbox judges it.

    Disabled by default: this is the fallback for papers whose author code is missing or
    does not run. Empty endpoint fields inherit `[design]`, so one vision key configures both.
    """

    enabled: bool = False
    base_url: str = ""
    # glm-5.3-flash is the newest vision model on the GLM coding endpoint (2026).
    model: str = "glm-5.3-flash"
    api_key_env: str = ""
    # GLM-5 models can spend the whole token budget on hidden reasoning and return
    # empty content; reconstruction wants code, not deliberation.
    disable_thinking: bool = True
    max_tokens: int = Field(default=8000, ge=512, le=32000)
    # Older vision models can still win on layout-heavy composites; when the primary
    # model does not reach L2, try this one and keep the better render.
    fallback_model: str = "glm-4.5v"
    # Require the generated script to read a real/synthetic table (GAXIS_DATA); a script
    # that hardcodes numbers only imitates pixels and is not reusable code.
    require_data: bool = True
    max_rounds: int = Field(default=3, ge=1, le=6)
    target_similarity: float = Field(default=0.85, ge=0.0, le=1.0)
    max_side: int = Field(default=1024, ge=256, le=2048)
    timeout_s: float = Field(default=300.0, gt=0, le=900)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class QualitySettings(BaseModel):
    """Extraction-quality weights (see src/gaxis/quality.py). Calibrated, not guessed."""

    caption: float = Field(default=0.28, ge=0.0, le=1.0)
    artwork: float = Field(default=0.18, ge=0.0, le=1.0)
    resolution: float = Field(default=0.14, ge=0.0, le=1.0)
    area: float = Field(default=0.09, ge=0.0, le=1.0)
    vector: float = Field(default=0.13, ge=0.0, le=1.0)
    cited: float = Field(default=0.08, ge=0.0, le=1.0)
    crop_clean: float = Field(default=0.10, ge=0.0, le=1.0)


class UsefulnessSettings(BaseModel):
    """Weights for the usefulness score (see src/gaxis/usefulness.py)."""

    journal: float = Field(default=0.35, ge=0.0, le=1.0)
    statistics: float = Field(default=0.20, ge=0.0, le=1.0)
    verification: float = Field(default=0.20, ge=0.0, le=1.0)
    panels: float = Field(default=0.15, ge=0.0, le=1.0)
    caption: float = Field(default=0.10, ge=0.0, le=1.0)


class RankingSettings(BaseModel):
    """How design and usefulness combine in retrieval (design leads)."""

    design_weight: float = Field(default=0.70, ge=0.0, le=1.0)
    usefulness_weight: float = Field(default=0.30, ge=0.0, le=1.0)


class SandboxSettings(BaseModel):
    """Isolation for running paper code (ADR-11: rootless podman)."""

    backend: Literal["podman", "local"] = "podman"
    image: str = "gaxis-repro:py312"
    autobuild: bool = True
    autobuild_packages: list[str] = Field(
        default_factory=lambda: ["matplotlib==3.11.2", "numpy==2.5.5"]
    )
    r_image: str = "gaxis-repro-r:4.5"
    r_base_image: str = "docker.io/rocker/tidyverse:4.5"
    r_packages: list[str] = Field(default_factory=lambda: ["svglite", "patchwork", "cowplot"])
    per_paper_env: bool = Field(
        default=True, description="build a derived image from the paper's own requirements"
    )
    network: bool = False
    memory: str = "4g"
    cpus: float = Field(default=2.0, gt=0, le=64)
    pids_limit: int = Field(default=256, gt=0)
    timeout_s: float = Field(default=300.0, gt=0, le=3600)
    allow_network: bool = False


class ReproductionSettings(BaseModel):
    """Grading thresholds for L1/L2/L3 (ADR-06/ADR-10)."""

    l1_similarity: float = Field(default=0.85, ge=0.0, le=1.0)
    l2_similarity: float = Field(default=0.55, ge=0.0, le=1.0)
    compare_size: int = Field(default=256, ge=64, le=1024)


class KnowledgeSettings(BaseModel):
    """gbrain wiring (see docs/gbrain-integration.md)."""

    enabled: bool = True
    source: str = "paper-kb"
    binary: str | None = Field(
        default=None, description="gbrain CLI path; defaults to PATH, then scripts/gbrain.sh"
    )
    gbrain_home: str | None = None
    types: list[str] = Field(default_factory=lambda: ["analysis"])
    timeout_s: float = Field(default=120.0, gt=0, le=3600)
    retries: int = Field(default=3, ge=0, le=10)
    auto_ingest: bool = True
    include_rejected_design: bool = Field(
        default=False, description="index pages whose design tier is 'reject'"
    )


class GaxisConfig(BaseModel):
    data_root: str | None = None
    confirmation: ConfirmationSettings = Field(default_factory=ConfirmationSettings)
    render: RenderSettings = Field(default_factory=RenderSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    quality: QualitySettings = Field(default_factory=QualitySettings)
    usefulness: UsefulnessSettings = Field(default_factory=UsefulnessSettings)
    ranking: RankingSettings = Field(default_factory=RankingSettings)
    design: DesignSettings = Field(default_factory=DesignSettings)
    reconstruct: ReconstructSettings = Field(default_factory=ReconstructSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    reproduction: ReproductionSettings = Field(default_factory=ReproductionSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)


ENV_OVERRIDES = {
    "GAXIS_CONFIRM_MODE": ("confirmation", "mode"),
    "GAXIS_CONFIRM_MIN_CONFIDENCE": ("confirmation", "min_confidence"),
    "GAXIS_INGEST_MODE": ("ingest", "default_mode"),
    "GAXIS_RENDER_TIMEOUT": ("render", "timeout_s"),
    "GAXIS_GBRAIN_HOME": ("knowledge", "gbrain_home"),
    "GAXIS_GBRAIN_BIN": ("knowledge", "binary"),
    "GAXIS_KB_ENABLED": ("knowledge", "enabled"),
    "GAXIS_CONTACT_EMAIL": ("ingest", "contact_email"),
    "GAXIS_SANDBOX_BACKEND": ("sandbox", "backend"),
    "GAXIS_SANDBOX_IMAGE": ("sandbox", "image"),
    "GAXIS_SANDBOX_TIMEOUT": ("sandbox", "timeout_s"),
}


def _coerce(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def config_path(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    env = os.environ.get("GAXIS_CONFIG")
    if env:
        return Path(env).expanduser()
    project = Path.cwd() / "gaxis.toml"
    if project.is_file():
        return project
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    user = xdg / "gaxis" / "config.toml"
    return user if user.is_file() else None


def load_config(path: Path | None = None) -> GaxisConfig:
    """Load (and validate) configuration. A broken config fails loudly, never silently."""
    source = config_path(path)
    raw: dict[str, Any] = {}
    if source is not None:
        if not source.is_file():
            raise GaxisError("config_not_found", f"config file not found: {source}")
        try:
            raw = tomllib.loads(source.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise GaxisError("config_invalid", f"{source}: {exc}") from exc
    data_root = os.environ.get("GAXIS_DATA_DIR")
    if data_root:
        raw["data_root"] = data_root
    for env_name, (section, key) in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        raw.setdefault(section, {})
        if not isinstance(raw[section], dict):  # pragma: no cover - defensive
            raise GaxisError("config_invalid", f"[{section}] must be a table")
        raw[section][key] = _coerce(value)
    try:
        return GaxisConfig.model_validate(raw)
    except ValidationError as exc:
        raise GaxisError(
            "config_invalid",
            f"invalid configuration in {source or 'environment'}: {exc.error_count()} error(s)",
            hint=str(exc).splitlines()[0] if str(exc) else "",
        ) from exc


@dataclass(frozen=True)
class Settings:
    """Process-wide settings, assembled from config + defaults."""

    config: GaxisConfig
    data_root: Path
    renders_dir: Path
    manifests_dir: Path
    envs_dir: Path
    reports_dir: Path
    render_timeout_s: float
    assets_dir: Path = field(default=Path("assets"))

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        config = load_config(path)
        root = (
            Path(config.data_root).expanduser().resolve()
            if config.data_root
            else (Path.cwd() / "data").resolve()
        )
        return cls(
            config=config,
            data_root=root,
            renders_dir=root / "renders",
            manifests_dir=root / "manifests",
            envs_dir=root / "envs",
            reports_dir=root / "reports",
            render_timeout_s=config.render.timeout_s,
            assets_dir=root / "assets",
        )


def settings(path: Path | None = None) -> Settings:
    return Settings.load(path)
