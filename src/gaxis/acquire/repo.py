"""Finding the code behind a paper: repository links in text, plotting scripts in repos.

Two heuristics, both conservative and explainable:

1. **Links** — `github.com/owner/repo`, GitLab, Bitbucket, Zenodo records. Deduplicated,
   with obvious documentation URLs (issues, wiki, badges) filtered out.
2. **Scripts** — filenames that look like figure code (`plot_*.py`, `figure*.R`) scored by
   plotting evidence in the content (matplotlib/ggplot calls, savefig/ggsave). Analysis
   scripts that merely import pandas rank last, so the KB gets figure code, not pipelines.

Nothing is executed here; reproduction stays behind `reproduce_chart_code` and the sandbox.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_OWNER = r"[A-Za-z0-9_.-]+"
REPO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github", re.compile(rf"https?://(?:www\.)?github\.com/({_OWNER})/({_OWNER})", re.I)),
    (
        "gitlab",
        re.compile(
            r"https?://(?:www\.)?gitlab\.com/([A-Za-z0-9_.\-/]+?)(?:\.git)?(?:\s|$|[),;])",
            re.I,
        ),
    ),
    (
        "bitbucket",
        re.compile(rf"https?://(?:www\.)?bitbucket\.org/({_OWNER})/({_OWNER})", re.I),
    ),
    ("zenodo", re.compile(r"https?://(?:www\.)?zenodo\.org/(?:record|records)/(\d+)", re.I)),
]
_IGNORED_TAIL = re.compile(
    r"^/(issues|pull|blob|tree|wiki|releases|actions|compare|sponsors|topics)(/|$)", re.I
)

PLOT_MARKERS = (
    "matplotlib",
    "pyplot",
    "seaborn",
    "plot(",
    "savefig",
    "ggplot",
    "ggsave",
    "geom_",
    "lattice",
    "plotly",
)
FIGURE_NAME = re.compile(
    r"(fig(ure)?|plot|panel|supp|chart|graph)[^/]*\.(py|r|rmd|ipynb)$", re.IGNORECASE
)
SCRIPT_SUFFIXES = {".py", ".r", ".rmd", ".ipynb"}


@dataclass(frozen=True)
class RepoLink:
    url: str
    host: str
    owner: str = ""
    repo: str = ""

    @property
    def name(self) -> str:
        return f"{self.owner}__{self.repo}" if self.owner else f"zenodo_{self.repo}"


@dataclass(frozen=True)
class ScriptCandidate:
    path: Path
    relative_path: str
    language: str
    score: float
    markers: tuple[str, ...] = ()


@dataclass
class RepoInventory:
    link: RepoLink
    local_path: Path | None = None
    license: str | None = None
    scripts: list[ScriptCandidate] = field(default_factory=list)
    error: str = ""


def find_repository_urls(text: str, *, limit: int = 8) -> list[RepoLink]:
    found: dict[str, RepoLink] = {}
    for host, pattern in REPO_PATTERNS:
        for match in pattern.finditer(text or ""):
            if host == "zenodo":
                url = f"https://zenodo.org/records/{match.group(1)}"
                found.setdefault(url, RepoLink(url=url, host=host, repo=match.group(1)))
                continue
            if host == "gitlab":
                path = match.group(1).rstrip(".:")
                parts = [part for part in path.split("/") if part]
                if len(parts) < 2:
                    continue
                owner, repo = parts[0], parts[1]
            else:
                owner, repo = match.group(1), match.group(2).rstrip(".:")
            # github.com/owner/repo/issues/3 is documentation, not the repository
            if _IGNORED_TAIL.match(text[match.end() : match.end() + 32]):
                continue
            url = f"https://{host}.com/{owner}/{repo}"
            if repo.lower() in {"github.com", "gitlab.com"}:
                continue
            found.setdefault(url, RepoLink(url=url, host=host, owner=owner, repo=repo))
            if len(found) >= limit:
                return list(found.values())
    return list(found.values())


def clone_repository(
    link: RepoLink,
    dest_root: Path,
    *,
    timeout_s: float = 120.0,
    max_mb: float = 200.0,
) -> Path:
    """Shallow clone (no history, blob limit) into ``dest_root/<owner>__<repo>@<sha8>``."""
    dest_root.mkdir(parents=True, exist_ok=True)
    work = dest_root / link.name
    if work.is_dir() and any(work.iterdir()):
        return work
    if link.host != "github":
        raise RuntimeError(f"cloning {link.host} repositories is not supported yet")
    url = f"{link.url}.git"
    try:
        completed = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:limit=1m",
                "--quiet",
                url,
                str(work),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git clone failed: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip().splitlines()[-1][:200])
    size_mb = sum(path.stat().st_size for path in work.rglob("*") if path.is_file()) / 1e6
    if size_mb > max_mb:
        raise RuntimeError(f"repository is {size_mb:.0f} MB, above the {max_mb:g} MB limit")
    return work


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def find_license(repo_path: Path) -> str | None:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.txt"):
        candidate = repo_path / name
        if candidate.is_file():
            text = _read_text(candidate, 4000)
            for licence in ("AGPL", "LGPL", "GPL", "Apache", "MIT", "BSD", "CC-BY", "CC0"):
                if licence.lower() in text.lower():
                    return licence
            return "unknown"
    return None


def scan_scripts(repo_path: Path, *, limit: int = 12) -> list[ScriptCandidate]:
    candidates: list[ScriptCandidate] = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        if any(part in {".git", "node_modules", "docs", "test", "tests"} for part in path.parts):
            continue
        text = _read_text(path)
        markers = tuple(marker for marker in PLOT_MARKERS if marker.lower() in text.lower())
        name_hit = bool(FIGURE_NAME.search(path.name))
        score = 0.0
        score += 0.5 if name_hit else 0.0
        score += min(0.4, 0.1 * len(markers))
        if "savefig" in text or "ggsave" in text:
            score += 0.2
        if score <= 0.2:
            continue
        suffix = path.suffix.lower()
        language = "python" if suffix == ".py" else "r" if suffix in {".r", ".rmd"} else "other"
        candidates.append(
            ScriptCandidate(
                path=path,
                relative_path=str(path.relative_to(repo_path)),
                language=language,
                score=round(min(score, 1.0), 2),
                markers=markers,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]


def inventory_repository(link: RepoLink, repo_path: Path) -> RepoInventory:
    return RepoInventory(
        link=link,
        local_path=repo_path,
        license=find_license(repo_path),
        scripts=scan_scripts(repo_path),
    )


def dependency_profile(repo_path: Path, *, language: str = "python", limit: int = 16) -> list[str]:
    """Pinned packages from the repository, best-effort but bounded.

    Only files a maintainer actually ships are read (requirements.txt, environment.yml,
    DESCRIPTION). Missing or malformed files yield an empty list: the caller records
    "no dependency profile" instead of inventing a stack.
    """
    packages: list[str] = []
    if language == "r":
        description = repo_path / "DESCRIPTION"
        if description.is_file():
            text = _read_text(description, 20_000)
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("Imports:", "Depends:", "Suggests:")):
                    continue
                payload = stripped.split(":", 1)[1]
                for item in payload.split(","):
                    name = re.split(r"[\s(]", item.strip())[0]
                    if name and name not in {"R", "base", "stats", "utils", "methods"}:
                        packages.append(name)
        return _dedupe(packages)[:limit]

    requirements = repo_path / "requirements.txt"
    if requirements.is_file():
        for line in _read_text(requirements, 20_000).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "-", "git+", "http")):
                continue
            name = re.split(r"[\s;#]", stripped)[0]
            if name:
                packages.append(name)
    environment = repo_path / "environment.yml"
    if environment.is_file():
        for line in _read_text(environment, 20_000).splitlines():
            match = re.match(r"\s*-\s*([A-Za-z0-9_.\-]+)(?:[=<>!].*)?$", line)
            if match and match.group(1) not in {"pip", "python", "defaults", "conda-forge"}:
                packages.append(match.group(1))
    return _dedupe(packages)[:limit]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = re.split(r"[=<>!]", value)[0].lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
