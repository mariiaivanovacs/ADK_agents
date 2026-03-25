# from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)

import base64
import json
import os
import re
import time
from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from google.adk.agents import Agent

try:
    import tomllib  # Python 3.11+
except Exception:
    tomllib = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"
RAW_GITHUB_BASE = "https://raw.githubusercontent.com"
MB = 1024 * 1024

# Python venvs typically expand 2–4x from raw wheel sizes due to compiled
# binaries and transitive dependencies pulled in at install time.
VENV_EXPANSION_FACTOR_LOW = 0.9
VENV_EXPANSION_FACTOR_HIGH = 1.15

REQUEST_TIMEOUT = 20
MAX_TREE_SCAN_FILES = 30
MAX_SCRIPT_SCAN_FILES = 25
MAX_BREAKDOWN_ITEMS = 40
MAX_LARGE_FILES = 20


def _gh_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RepoWeightAgent/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Heuristics: installed size estimates (MB)
# ---------------------------------------------------------------------------

_KNOWN_PACKAGE_SIZES_MB: dict[str, float] = {
    # ML / AI — large installed footprints (include compiled binaries + transitive deps)
    "transformers": 500,
    "torch": 800,
    "torchaudio": 200,
    "torchvision": 200,
    "tensorflow": 600,
    "keras": 50,
    "jax": 300,
    "diffusers": 200,
    "sentence-transformers": 400,
    "openai": 5,
    "anthropic": 5,
    "langchain": 50,
    "llama-cpp-python": 200,
    # Data science — numpy/pandas include compiled C extensions + transitive deps
    "numpy": 120,    # raw wheel ~15 MB, installed ~120 MB with binaries
    "pandas": 180,   # pulls in numpy + dateutil + pytz; installed ~180 MB
    "scipy": 200,    # heavy BLAS/LAPACK compiled extensions
    "scikit-learn": 120,
    "matplotlib": 80,
    "seaborn": 10,
    "plotly": 40,
    "jupyter": 200,
    "notebook": 150,
    # Native compiled (binary expansion at install time)
    "regex": 10,         # compiled C extension
    "tls-client": 30,    # ships platform binaries
    "cryptography": 20,
    "lxml": 15,
    "pydantic": 10,
    # Web / API
    "fastapi": 5,
    "django": 20,
    "flask": 5,
    "uvicorn": 2,
    "requests": 1,
    "httpx": 2,
    # Browser / automation — trigger large binary downloads
    "playwright": 200,   # +browser binaries (~150–300 MB on first run)
    "selenium": 100,
    "puppeteer": 250,
    # Databases
    "psycopg2": 5,
    "sqlalchemy": 10,
    "pymongo": 5,
    "redis": 2,
    "firebase-admin": 30,
    # Cloud / infra
    "boto3": 20,
    "google-cloud-storage": 10,
    "google-cloud-bigquery": 15,
    "azure-storage-blob": 10,
    # Media / NLP
    "pillow": 15,
    "opencv-python": 200,
    "librosa": 30,
    "nltk": 50,
    "spacy": 100,
    # Node.js defaults
    "_node_modules_default": 200,
    # Rust / Go / Java defaults
    "_generic_small": 5,
    "_generic_medium": 20,
}

_DEFAULT_PACKAGE_SIZE_MB = 5


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def _parse_github_url(url: str) -> tuple[str, str]:
    """Returns (owner, repo) from a GitHub URL, stripping .git suffix."""
    url = url.strip().rstrip("/")
    path = urlparse(url).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse GitHub URL: {url}")
    owner, repo = parts[0], parts[1]
    return owner, repo


def _request_json(url: str, headers: dict[str, str] | None = None, timeout: int = REQUEST_TIMEOUT) -> Any | None:
    """Small retry wrapper for GitHub/API calls."""
    headers = headers or {}
    backoff = 1.0

    for attempt in range(4):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()

            # Common retryable cases
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff)
                backoff *= 2
                continue

            # 403 can be rate limit or permission issue
            if resp.status_code == 403:
                text = resp.text.lower()
                if "rate limit" in text or "secondary rate limit" in text:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return None

            if resp.status_code == 404:
                return None

            return None
        except requests.RequestException:
            if attempt == 3:
                return None
            time.sleep(backoff)
            backoff *= 2

    return None


@lru_cache(maxsize=256)
def _gh_get(path: str) -> Any | None:
    url = f"{GITHUB_API_BASE}{path}"
    return _request_json(url, headers=_gh_headers())


@lru_cache(maxsize=128)
def _get_repo_info(owner: str, repo: str) -> dict[str, Any] | None:
    data = _gh_get(f"/repos/{owner}/{repo}")
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=128)
def _get_default_branch_tree(owner: str, repo: str) -> tuple[str, list[dict[str, Any]], bool] | None:
    """
    Returns (default_branch, tree_items, truncated).
    Uses branch ref -> commit -> tree SHA so the GitHub Trees API is correct.
    """
    repo_info = _get_repo_info(owner, repo)
    if not repo_info:
        return None

    branch = repo_info.get("default_branch", "main")
    ref = _gh_get(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
    if not isinstance(ref, dict):
        return None

    commit_sha = (ref.get("object") or {}).get("sha")
    if not commit_sha:
        return None

    commit = _gh_get(f"/repos/{owner}/{repo}/git/commits/{commit_sha}")
    if not isinstance(commit, dict):
        return None

    tree_sha = (commit.get("tree") or {}).get("sha")
    if not tree_sha:
        return None

    tree_data = _gh_get(f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1")
    if not isinstance(tree_data, dict):
        return None

    items = tree_data.get("tree", [])
    truncated = bool(tree_data.get("truncated", False))
    if not isinstance(items, list):
        return None

    return branch, items, truncated


def _fetch_tree(owner: str, repo: str) -> list[dict[str, Any]]:
    tree_pack = _get_default_branch_tree(owner, repo)
    if not tree_pack:
        return []
    _, items, _ = tree_pack
    return [item for item in items if item.get("type") == "blob"]


def _fetch_default_branch(owner: str, repo: str) -> str:
    repo_info = _get_repo_info(owner, repo)
    if not repo_info:
        return "main"
    return repo_info.get("default_branch", "main")


@lru_cache(maxsize=256)
def _fetch_file_content(owner: str, repo: str, file_path: str) -> Optional[str]:
    """
    Fetch file content from GitHub contents API.
    Falls back to download_url for larger files.
    """
    data = _gh_get(f"/repos/{owner}/{repo}/contents/{file_path}")
    if not isinstance(data, dict):
        return None

    if data.get("encoding") == "base64" and data.get("content"):
        try:
            raw = base64.b64decode(data["content"])
            return raw.decode("utf-8", errors="replace")
        except Exception:
            pass

    download_url = data.get("download_url")
    if download_url:
        try:
            resp = requests.get(download_url, headers={"User-Agent": "RepoWeightAgent/1.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            return None

    return data.get("content")


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

def _normalize_pkg_name(raw: str) -> str:
    raw = raw.strip().lower()
    raw = raw.split(";")[0].strip()
    raw = raw.split("[")[0].strip()
    raw = re.split(r"[<>=!~\s]", raw)[0].strip()
    raw = raw.replace("_", "-")
    return raw


def _package_size(pkg: str) -> float:
    return _KNOWN_PACKAGE_SIZES_MB.get(pkg, _DEFAULT_PACKAGE_SIZE_MB)


def _parse_manifest_name_from_path(path: str) -> str:
    return os.path.basename(path).lower()


# ---------------------------------------------------------------------------
# Dependency / install size estimation
# ---------------------------------------------------------------------------
# Python parsers return list[str] of package names so the caller can
# deduplicate across multiple manifests before summing sizes.
# Non-Python parsers stay count-based and return (float, list[str]).
# ---------------------------------------------------------------------------

def _parse_packages_from_requirements(content: str) -> list[str]:
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = _normalize_pkg_name(line)
        if pkg:
            packages.append(pkg)
    return packages


def _parse_packages_from_conda(content: str) -> list[str]:
    packages = []
    in_deps = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip("\n")
        if line.strip().startswith("dependencies:"):
            in_deps = True
            continue
        if in_deps:
            if line and not line[0].isspace():
                in_deps = False
                continue
            stripped = line.strip().lstrip("- ").strip()
            if not stripped or stripped == "pip":
                continue
            stripped = stripped.split("::")[-1]
            pkg = _normalize_pkg_name(stripped)
            if pkg:
                packages.append(pkg)
    return packages


def _parse_packages_from_pyproject(content: str) -> list[str]:
    """PEP 621 and Poetry pyproject.toml — returns package names only."""
    packages: list[str] = []

    if tomllib is not None:
        try:
            data = tomllib.loads(content)
            project = data.get("project", {})
            for dep in project.get("dependencies", []) or []:
                pkg = _normalize_pkg_name(str(dep))
                if pkg:
                    packages.append(pkg)
            for _, dep_list in (project.get("optional-dependencies", {}) or {}).items():
                for dep in dep_list or []:
                    pkg = _normalize_pkg_name(str(dep))
                    if pkg:
                        packages.append(pkg)
            poetry_deps = (((data.get("tool", {}) or {}).get("poetry", {}) or {}).get("dependencies", {}) or {})
            poetry_dev = (((data.get("tool", {}) or {}).get("poetry", {}) or {}).get("group", {}) or {})
            for name in poetry_deps.keys():
                if name.lower() != "python":
                    packages.append(_normalize_pkg_name(name))
            for _, group_data in poetry_dev.items():
                for name in ((group_data or {}).get("dependencies", {}) or {}).keys():
                    packages.append(_normalize_pkg_name(name))
        except Exception:
            packages = []

    if not packages:
        for match in re.finditer(r"(?m)^\s*([A-Za-z0-9_.\-]+)\s*=", content):
            name = match.group(1).strip().lower()
            if name not in {"build-system", "tool", "project", "name", "version", "description"}:
                packages.append(_normalize_pkg_name(name))

    return [p for p in packages if p and p != "python"]


def _parse_packages_from_pipfile(content: str) -> list[str]:
    packages = []
    in_section = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line in ("[packages]", "[dev-packages]"):
            in_section = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = False
            continue
        if in_section and not line.startswith("#") and "=" in line:
            name = line.split("=", 1)[0].strip()
            pkg = _normalize_pkg_name(name)
            if pkg:
                packages.append(pkg)
    return packages


def _python_manifest_packages(path: str, content: str) -> list[str] | None:
    """
    Returns package names for Python manifests, or None for non-Python ones.
    Caller deduplicates across all manifests before sizing.
    """
    name = _parse_manifest_name_from_path(path)
    if name in {"requirements.txt", "requirements-dev.txt", "requirements-prod.txt"}:
        return _parse_packages_from_requirements(content)
    if name in {"environment.yml", "environment.yaml"}:
        return _parse_packages_from_conda(content)
    if name == "pyproject.toml":
        return _parse_packages_from_pyproject(content)
    if name == "pipfile":
        return _parse_packages_from_pipfile(content)
    return None


def _size_unique_packages(packages: list[str]) -> tuple[float, list[str]]:
    """Deduplicate package names then sum installed-footprint sizes."""
    seen: set[str] = set()
    unique = []
    for pkg in packages:
        if pkg and pkg not in seen:
            seen.add(pkg)
            unique.append(pkg)
    total = 0.0
    breakdown = []
    for pkg in unique:
        size = _package_size(pkg)
        total += size
        breakdown.append(f"{pkg}: ~{size:.0f} MB")
    return total, breakdown


def _estimate_from_package_json(content: str) -> tuple[float, list[str]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return 0.0, []
    deps: dict[str, str] = {}
    deps.update(data.get("dependencies", {}) or {})
    deps.update(data.get("devDependencies", {}) or {})
    count = len(deps)
    if count == 0:
        return 0.0, []
    total = _KNOWN_PACKAGE_SIZES_MB["_node_modules_default"] + count * 2
    return total, [f"node_modules ({count} packages): ~{total:.0f} MB"]


def _estimate_from_go_mod(content: str) -> tuple[float, list[str]]:
    """
    Go modules are often smaller than Python/ML stacks, but dependencies still matter.
    Very rough estimate based on count.
    """
    deps = set()

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("require "):
            continue
        if line.startswith("module ") or line.startswith("go "):
            continue
        if re.match(r"^[A-Za-z0-9_.\-\/]+(\s+v\d+.*)?$", line):
            parts = line.split()
            if parts:
                deps.add(parts[0])

    count = len(deps)
    if count == 0:
        return 0.0, []

    total = _KNOWN_PACKAGE_SIZES_MB["_generic_small"] + count * 3
    return total, [f"go modules ({count} modules): ~{total:.0f} MB"]


def _estimate_from_cargo_toml(content: str) -> tuple[float, list[str]]:
    deps = []
    in_deps = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("[dependencies]") or line.startswith("[dev-dependencies]"):
            in_deps = True
            continue
        if line.startswith("[") and line.endswith("]") and line not in ("[dependencies]", "[dev-dependencies]"):
            in_deps = False
            continue
        if in_deps and "=" in line and not line.startswith("#"):
            name = line.split("=", 1)[0].strip()
            if name:
                deps.append(_normalize_pkg_name(name))

    deps = [d for d in dict.fromkeys(deps) if d]
    if not deps:
        return 0.0, []

    total = _KNOWN_PACKAGE_SIZES_MB["_generic_small"] + len(deps) * 4
    return total, [f"cargo crates ({len(deps)} crates): ~{total:.0f} MB"]


def _estimate_from_maven_or_gradle(content: str) -> tuple[float, list[str]]:
    """
    Very rough estimate for Java build files.
    """
    deps = set()

    for line in content.splitlines():
        if "implementation" in line or "compile" in line or "dependency" in line:
            deps.add(line.strip())

    if not deps:
        return 0.0, []

    total = _KNOWN_PACKAGE_SIZES_MB["_generic_medium"] + len(deps) * 8
    return total, [f"java deps ({len(deps)} entries): ~{total:.0f} MB"]


def _non_python_manifest_estimate(path: str, content: str) -> tuple[float, list[str]]:
    """Count-based estimates for non-Python ecosystems."""
    name = _parse_manifest_name_from_path(path)
    if name == "package.json":
        return _estimate_from_package_json(content)
    if name == "go.mod":
        return _estimate_from_go_mod(content)
    if name == "cargo.toml":
        return _estimate_from_cargo_toml(content)
    if name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
        return _estimate_from_maven_or_gradle(content)
    return 0.0, []


def _detect_manifest_files(tree: list[dict[str, Any]]) -> list[str]:
    manifest_names = {
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-prod.txt",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "package.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "package-lock.json",
        "environment.yml",
        "environment.yaml",
        "Pipfile",
        "Pipfile.lock",
        "go.mod",
        "Cargo.toml",
        "Cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    }
    return [
        item["path"]
        for item in tree
        if item.get("type") == "blob" and (
            os.path.basename(item["path"]) in manifest_names or item["path"] in manifest_names
        )
    ]


def _scan_large_file_hints(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Returns large tracked files from the repo tree itself.
    """
    large_files = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        size = int(item.get("size") or 0)
        path = item.get("path", "")
        if size >= 10 * MB:
            large_files.append(
                {
                    "path": path,
                    "size_bytes": size,
                    "size_mb": round(size / MB, 2),
                }
            )
    large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return large_files[:MAX_LARGE_FILES]


# ---------------------------------------------------------------------------
# Hidden asset / download signal scanning
# ---------------------------------------------------------------------------

def _line_hits(text: str, pattern: str, label: str) -> list[dict[str, Any]]:
    hits = []
    for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        line = text.splitlines()[line_no - 1].strip()
        hits.append(
            {
                "line": line_no,
                "label": label,
                "snippet": line[:300],
            }
        )
    return hits


def _scan_for_large_assets(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    patterns = [
        (r"^\s*(wget|curl)\b.*\.(bin|pt|pth|ckpt|safetensors|gguf|h5|pb|onnx|zip|tar|tgz|gz)\b", "direct model/data download"),
        (r"huggingface_hub\.hf_hub_download|from_pretrained\(", "HuggingFace model load/download"),
        (r"\b(load_dataset|datasets\.load_dataset)\(", "dataset download"),
        (r"\bgdown\b|drive\.google\.com", "Google Drive download"),
        (r"\bapt(-get)?\s+install\b", "apt package install"),
        (r"\bbrew\s+install\b", "brew package install"),
        (r"\bpip\s+install\b", "pip install in script"),
        (r"\bdocker\s+pull\b", "docker image pull"),
        (r"version\s+https://git-lfs\.github\.com/spec/v1", "Git LFS pointer"),
    ]

    for pattern, label in patterns:
        hits.extend(_line_hits(text, pattern, label))

    # Additional file-type hint if the line references likely large artifacts
    extra_patterns = [
        (r"\.(safetensors|gguf|ckpt|pth|pt|onnx|bin|zip|tar|gz|h5|pb)\b", "large artifact filename"),
    ]
    for pattern, label in extra_patterns:
        hits.extend(_line_hits(text, pattern, label))

    # Deduplicate a bit
    unique = []
    seen = set()
    for hit in hits:
        key = (hit["line"], hit["label"], hit["snippet"])
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    return unique


def _candidate_scan_files(tree: list[dict[str, Any]]) -> list[str]:
    candidates = []
    for item in tree:
        path = item.get("path", "")
        base = os.path.basename(path).lower()

        if item.get("type") != "blob":
            continue

        if any(path.endswith(ext) for ext in (".sh", ".bash", ".zsh", ".py", ".rb", ".js", ".ts", ".tsx", ".jsx", ".ps1")):
            candidates.append(path)
            continue

        if base in {
            "readme.md",
            "readme.rst",
            "readme.txt",
            "install.md",
            "requirements.md",
            "requirements.txt",
            "setup.py",
            "setup.cfg",
            "pyproject.toml",
            "makefile",
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "environment.yml",
            "environment.yaml",
            "package.json",
            "pipfile",
            "go.mod",
            "cargo.toml",
        }:
            candidates.append(path)

    # Prefer docs/scripts/manifests
    return candidates[:MAX_SCRIPT_SCAN_FILES]


def _asset_size_hint_from_signal(signal: dict[str, Any]) -> tuple[float, float]:
    """
    Returns (min_mb, max_mb) hint for a signal.
    Keep this broad to avoid false precision.
    """
    label = signal.get("label", "").lower()
    snippet = signal.get("snippet", "").lower()

    if "git lfs" in label:
        return 50.0, 5000.0
    if "huggingface model" in label or "model" in label:
        return 100.0, 10000.0
    if "dataset" in label:
        return 100.0, 100000.0
    if "docker image" in label:
        return 100.0, 2000.0
    if "apt package" in label or "brew package" in label:
        return 20.0, 300.0
    if "pip install" in label:
        # usually install footprint already counted in manifests; keep tiny
        return 0.0, 0.0
    if "drive" in label:
        return 100.0, 10000.0

    if any(ext in snippet for ext in [".safetensors", ".gguf", ".ckpt", ".pth", ".pt", ".onnx", ".bin"]):
        return 100.0, 10000.0

    return 0.0, 0.0


# ---------------------------------------------------------------------------
# ADK tools
# ---------------------------------------------------------------------------

def github_static_analyzer(repo_url: str) -> str:
    """
    Returns a JSON report with:
      - actual tracked repo size from GitHub blobs
      - largest tracked files
      - detected manifest files
      - estimated installation footprint from manifests
    """
    try:
        owner, repo = _parse_github_url(repo_url)
    except ValueError as e:
        return json.dumps({"error": str(e)}, indent=2)

    tree_pack = _get_default_branch_tree(owner, repo)
    if not tree_pack:
        return json.dumps(
            {
                "error": "Could not fetch repository tree. Check the URL, repo visibility, or GITHUB_TOKEN.",
                "repo": f"{owner}/{repo}",
            },
            indent=2,
        )

    branch, tree_items, truncated = tree_pack
    blobs = [item for item in tree_items if item.get("type") == "blob"]

    tracked_bytes = sum(int(item.get("size") or 0) for item in blobs)
    tracked_mb = tracked_bytes / MB

    manifests = _detect_manifest_files(blobs)
    manifest_details: list[dict[str, Any]] = []

    # Collect Python package names across all manifests, then deduplicate before sizing.
    all_python_packages: list[str] = []
    dep_total_mb = 0.0
    dep_breakdown: list[str] = []

    for manifest_path in manifests:
        content = _fetch_file_content(owner, repo, manifest_path)
        if not content:
            manifest_details.append({"path": manifest_path, "status": "unreadable"})
            continue

        pkgs = _python_manifest_packages(manifest_path, content)
        if pkgs is not None:
            all_python_packages.extend(pkgs)
            manifest_details.append({"path": manifest_path, "status": "parsed (python)"})
        else:
            est_mb, breakdown = _non_python_manifest_estimate(manifest_path, content)
            dep_total_mb += est_mb
            dep_breakdown.extend([f"[{manifest_path}] {b}" for b in breakdown])
            manifest_details.append({"path": manifest_path, "estimated_install_mb": round(est_mb, 2), "status": "parsed"})

    # Size Python deps once from the deduplicated set.
    python_mb, python_breakdown = _size_unique_packages(all_python_packages)
    dep_total_mb += python_mb
    dep_breakdown.extend([f"[python] {b}" for b in python_breakdown])

    largest_files = _scan_large_file_hints(blobs)

    # Narrow uncertainty band: table already holds installed-footprint values, not raw wheels.
    dep_low_mb = dep_total_mb * VENV_EXPANSION_FACTOR_LOW
    dep_high_mb = dep_total_mb * VENV_EXPANSION_FACTOR_HIGH

    report = {
        "repo": f"{owner}/{repo}",
        "default_branch": branch,
        "tree_truncated": truncated,
        "files_found": len(blobs),
        "tracked_repo_size": {
            "bytes": tracked_bytes,
            "mb": round(tracked_mb, 2),
            "gb": round(tracked_mb / 1024, 2),
        },
        "largest_tracked_files": largest_files,
        "manifests_found": manifest_details,
        "estimated_install_footprint_mb": {
            "raw_manifest_sum": round(dep_total_mb, 2),
            "realistic_low": round(dep_low_mb, 2),
            "realistic_high": round(dep_high_mb, 2),
            "why": "±10-15% band accounts for minor version differences and optional compiled extras",
        },
        "estimated_total_after_install_mb": {
            "low": round(tracked_mb + dep_low_mb, 2),
            "high": round(tracked_mb + dep_high_mb, 2),
        },
        "dependency_breakdown": dep_breakdown[:MAX_BREAKDOWN_ITEMS],
        "notes": [
            "tracked_repo_size is based on GitHub blob sizes, not guessed package weights",
            "estimated_install_footprint is based on manifests and is only approximate",
            "realistic range is a narrow ±10-15% band since package table already reflects installed sizes",
        ],
    }

    return json.dumps(report, indent=2, ensure_ascii=False)


def script_parser(repo_url: str) -> str:
    """
    Scans scripts and docs for hidden downloads and large asset clues.
    Returns a JSON report with matched lines.
    """
    try:
        owner, repo = _parse_github_url(repo_url)
    except ValueError as e:
        return json.dumps({"error": str(e)}, indent=2)

    tree_pack = _get_default_branch_tree(owner, repo)
    if not tree_pack:
        return json.dumps(
            {"error": "Could not fetch repository tree.", "repo": f"{owner}/{repo}"},
            indent=2,
        )

    _, tree_items, _ = tree_pack
    scan_targets = _candidate_scan_files(tree_items)

    all_hits: list[dict[str, Any]] = []
    scanned_files: list[str] = []

    for file_path in scan_targets:
        content = _fetch_file_content(owner, repo, file_path)
        if not content:
            continue
        scanned_files.append(file_path)
        hits = _scan_for_large_assets(content)
        for hit in hits:
            all_hits.append(
                {
                    "file": file_path,
                    **hit,
                }
            )

    # Aggregate estimated asset range from signals
    min_mb = 0.0
    max_mb = 0.0
    for hit in all_hits:
        lo, hi = _asset_size_hint_from_signal(hit)
        min_mb += lo
        max_mb += hi

    # Deduplicate by file+line+snippet
    seen = set()
    deduped = []
    for hit in all_hits:
        key = (hit["file"], hit["line"], hit["label"], hit["snippet"])
        if key not in seen:
            seen.add(key)
            deduped.append(hit)

    report = {
        "repo": f"{owner}/{repo}",
        "files_scanned": len(scanned_files),
        "scanned_files": scanned_files,
        "hidden_asset_signals": deduped[:MAX_BREAKDOWN_ITEMS],
        "estimated_hidden_asset_download_mb": {
            "min": round(min_mb, 2),
            "max": round(max_mb, 2),
        },
        "notes": [
            "This tool looks for clues about extra downloads, model weights, datasets, and system installs.",
            "It does not prove assets exist; it only finds textual signals.",
        ],
    }

    return json.dumps(report, indent=2, ensure_ascii=False)


def browser_use_search(query: str, repo_url: str) -> str:
    """
    Optional external verification through Browser Use.
    Use only when the static analysis is uncertain or incomplete.
    """
    browser_key = os.getenv("BROWSER_USE_API_KEY", "").strip()
    if not browser_key:
        return json.dumps(
            {
                "error": "BROWSER_USE_API_KEY not set",
                "suggestion": f"Search manually for '{repo_url} {query}'",
            },
            indent=2,
        )

    endpoint = "https://api.browser-use.com/api/v1/run-sync"
    task = (
        f"Visit this GitHub repository: {repo_url}\n"
        f"Look for: {query}\n"
        "Check these locations in order:\n"
        "1. README.md installation / requirements / hardware sections\n"
        "2. Wiki pages if available\n"
        "3. Any INSTALL.md / REQUIREMENTS.md / docs pages\n"
        "Return any explicit disk, RAM, GPU, model, or dataset size information."
    )

    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {browser_key}",
                "Content-Type": "application/json",
                "User-Agent": "RepoWeightAgent/1.0",
            },
            json={"task": task},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result") or data.get("output") or data
            return json.dumps({"result": result}, indent=2, ensure_ascii=False)

        return json.dumps(
            {
                "error": f"Browser Use API returned {resp.status_code}",
                "detail": resp.text[:1000],
            },
            indent=2,
            ensure_ascii=False,
        )
    except requests.RequestException as e:
        return json.dumps({"error": f"Browser Use API request failed: {e}"}, indent=2)


# ---------------------------------------------------------------------------
# Root agent
# ---------------------------------------------------------------------------

root_agent = Agent(
    name="RepoWeightAgent",
    model="gemini-2.5-flash",
    instruction="""
You are RepoWeightBuddy, a DevOps assistant that estimates two things for a GitHub repository:

1) The actual tracked repository size from GitHub blob sizes.
2) The realistic installation footprint from dependency manifests and extra downloads.

Workflow for each GitHub URL:
- Call github_static_analyzer first.
- Then call script_parser.
- Call browser_use_search only if static signals are ambiguous or confidence is below 70%.
- Never invent sizes — use JSON data from the tools.

Confidence rules:
- High (80%+): standard manifest found, no ML/browser packages
- Medium (50-79%): some packages unknown, or heavy libs (numpy, pandas, torch) detected
- Low (<50%): no manifest found, or model/dataset downloads detected

Final answer must follow this exact structure:

1) Repo size (approximation range)
   State the tracked repo clone size and the realistic install range from estimated_total_after_install_mb.
   Example: "Clone: 0.4 MB | After install: ~250 MB – 500 MB"

2) Identified files and lines that explain large sizes
   List manifest files found and quote specific lines or package names that drive up the size.
   Flag heavy classes: numpy/pandas (compiled C extensions), playwright/selenium (browser binaries), torch/tensorflow (large wheels), model/dataset downloads.

3) Brief project description
   One or two sentences on what the project does.

Key insight to communicate when relevant:
Static manifest analysis underestimates real venv size by 1.5–2.5x because compiled libraries
and transitive dependencies expand at install time. Always show the range, not a single number.
""".strip(),
    tools=[github_static_analyzer, script_parser, browser_use_search],
)