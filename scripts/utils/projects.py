"""
Shared project package helpers for Deaner-HD.

Project packages keep one video's outline, metadata, and clips together so Dean
does not need to navigate a technical folder tree.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = PROJECT_ROOT / "02_Projects"
CLIPS_DIR = PROJECT_ROOT / "clips"
LEGACY_PROJECTS_DIR = PROJECT_ROOT / "pipeline" / "projects"


def slugify(text: str, max_len: int = 60) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:max_len].strip("-") or "video"


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    slug: str
    script_dir: Path
    metadata_dir: Path
    notes_dir: Path
    raw_clips_dir: Path
    drafts_dir: Path
    assets_dir: Path
    scorecards_dir: Path
    screenshots_dir: Path
    timeline_dir: Path
    simple_layout: bool = False

    @property
    def package_slug(self) -> str:
        return slugify(self.root.name, max_len=80)

    @property
    def script_path(self) -> Path:
        if self.simple_layout:
            return self.root / "01_outline.md"
        return self.script_dir / f"{self.package_slug}-script.md"

    @property
    def metadata_path(self) -> Path:
        if self.simple_layout:
            return self.root / "03_metadata.txt"
        return self.metadata_dir / f"{self.package_slug}-metadata.txt"

    @property
    def requirements_path(self) -> Path:
        if self.simple_layout:
            return self.root / "00_READ_ME.md"
        return self.notes_dir / f"{self.package_slug}-requirements.md"

    @property
    def proof_path(self) -> Path:
        return self.notes_dir / f"{self.package_slug}-proof.md"

def resolve_project(project: str | Path | None, seed: str = "video", create: bool = False) -> ProjectPaths | None:
    """
    Resolve a project slug or path to the canonical package shape.

    - Existing absolute/relative paths are used directly.
    - Bare slugs are created under 02_Projects/YYYY-MM-DD-slug unless
      a matching package already exists.
    - Returns None when no project was requested so callers can keep flat
      backwards-compatible behavior.
    """
    if not project:
        return None

    project_text = str(project).strip()
    today = datetime.date.today().isoformat()
    slug_seed = slugify(project_text or seed)

    raw_path = Path(project_text).expanduser()
    is_path = (
        raw_path.is_absolute()
        or raw_path.parts[:2] in {("pipeline", "projects"), ("02_Projects",)}
        or "/" in project_text
    )
    if is_path:
        root = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
        slug = slugify(root.name.removeprefix(f"{today}-"))
    else:
        exact_root = PROJECTS_DIR / project_text
        matches = sorted(PROJECTS_DIR.glob(f"*-{slug_seed}"))
        if not matches and LEGACY_PROJECTS_DIR.exists():
            matches = sorted(LEGACY_PROJECTS_DIR.glob(f"*-{slug_seed}"))
        root = exact_root if exact_root.exists() else (matches[-1] if matches else PROJECTS_DIR / f"{today}-{slug_seed}")
        slug = slug_seed

    simple_layout = PROJECTS_DIR in root.parents or root == PROJECTS_DIR or root.parts[:1] == ("02_Projects",)
    paths = ProjectPaths(
        root=root,
        slug=slug,
        script_dir=root if simple_layout else root / "script",
        metadata_dir=root if simple_layout else root / "metadata",
        notes_dir=root if simple_layout else root / "notes",
        raw_clips_dir=CLIPS_DIR / root.name / "raw" if simple_layout else root / "clips" / "raw",
        drafts_dir=root / "_drafts",
        assets_dir=root / "source_assets" if simple_layout else root / "assets",
        scorecards_dir=root / "source_assets" / "scorecards" if simple_layout else root / "assets" / "scorecards",
        screenshots_dir=root / "source_assets" / "screenshots" if simple_layout else root / "assets" / "screenshots",
        timeline_dir=root / "timeline" if simple_layout else root / "timeline",
        simple_layout=simple_layout,
    )

    if create:
        directories = [
            paths.script_dir,
            paths.metadata_dir,
            paths.raw_clips_dir,
        ]
        if not paths.simple_layout:
            directories.extend([paths.scorecards_dir, paths.screenshots_dir])
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    return paths


def latest_script(project: ProjectPaths | None, fallback_dir: Path) -> Path | None:
    if project:
        if project.simple_layout:
            candidates = []
            for name in ("01_outline.md", "02_script.md"):
                path = project.root / name
                if path.exists():
                    text = path.read_text(encoding="utf-8", errors="ignore").strip()
                    if text and "Use this only when a word-for-word script is requested" not in text:
                        candidates.append(path)
            if candidates:
                return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        if project.script_path.exists():
            return project.script_path
        files = sorted(project.script_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return files[0]
    files = sorted(fallback_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def write_default_requirements(project: ProjectPaths, title: str = "") -> None:
    if project.requirements_path.exists():
        return
    topic = title or project.slug.replace("-", " ")
    if project.simple_layout:
        project.requirements_path.write_text(
            f"# Project: {topic}\n\n"
            "## Status\n\n"
            "- Outline: not started\n"
            "- Metadata: not started\n"
            "- Clips gathered: not started\n"
            "- Final edit: manual in Dean's editor\n\n"
            "## Simple Workflow\n\n"
            "1. Write or approve `01_outline.md`.\n"
            "2. Gather clips into the matching folder under `clips/`.\n"
            "3. Use `04_clip_cue_sheet.csv` and the gathered clips for manual editing.\n"
            "4. Use `03_metadata.txt` for upload copy.\n\n"
            "## Promise\n\n"
            "This folder is an edit-ready production package. Final editing is manual.\n",
            encoding="utf-8",
        )
    else:
        project.requirements_path.write_text(
            f"# Requirements: {topic}\n\n"
            "## Workflow\n"
            "1. Script and metadata are generated before clip gathering.\n"
            "2. Clips are gathered from script cues, then manually approved.\n"
            "3. Voiceover must complete naturally; never cut mid-sentence.\n"
            "4. Final export lives in this package's `exports/` folder.\n\n"
            "## Visual Rules\n"
            "- Use real game footage, relevant interviews, and relevant training/workout clips.\n"
            "- Reject gameplay, simulations, fan hosts, podcast panels, subscribe/like overlays, creator title cards, and unrelated faces.\n\n"
            "## Final Checks\n"
            "- Full audio completed.\n"
            "- No b-roll looping.\n"
            "- No abrupt ending.\n"
            "- No adjacent same-source clips when avoidable.\n",
            encoding="utf-8",
        )
