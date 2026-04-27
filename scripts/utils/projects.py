"""
Shared project package helpers for Deaner-HD.

Project packages keep one video's script, metadata, clips, voiceover, exports,
and proof notes together so Dean does not need to remember loose filenames.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = PROJECT_ROOT / "pipeline" / "projects"


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
    thumbnail_dir: Path
    notes_dir: Path
    raw_clips_dir: Path
    approved_clips_dir: Path
    voiceover_dir: Path
    exports_dir: Path
    drafts_dir: Path
    assets_dir: Path
    scorecards_dir: Path
    screenshots_dir: Path
    timeline_dir: Path

    @property
    def package_slug(self) -> str:
        return slugify(self.root.name, max_len=80)

    @property
    def script_path(self) -> Path:
        return self.script_dir / f"{self.package_slug}-script.md"

    @property
    def metadata_path(self) -> Path:
        return self.metadata_dir / f"{self.package_slug}-metadata.txt"

    @property
    def thumbnail_path(self) -> Path:
        return self.thumbnail_dir / f"{self.package_slug}-thumbnail-brief.txt"

    @property
    def requirements_path(self) -> Path:
        return self.notes_dir / f"{self.package_slug}-requirements.md"

    @property
    def proof_path(self) -> Path:
        return self.notes_dir / f"{self.package_slug}-proof.md"

    @property
    def final_video_path(self) -> Path:
        return self.exports_dir / f"{self.package_slug}-final.mp4"


def resolve_project(project: str | Path | None, seed: str = "video", create: bool = False) -> ProjectPaths | None:
    """
    Resolve a project slug or path to the canonical package shape.

    - Existing absolute/relative paths are used directly.
    - Bare slugs are created under pipeline/projects/YYYY-MM-DD-slug unless
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
    if raw_path.is_absolute() or raw_path.parts[:2] == ("pipeline", "projects") or "/" in project_text:
        root = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
        slug = slugify(root.name.removeprefix(f"{today}-"))
    else:
        matches = sorted(PROJECTS_DIR.glob(f"*-{slug_seed}"))
        root = matches[-1] if matches else PROJECTS_DIR / f"{today}-{slug_seed}"
        slug = slug_seed

    paths = ProjectPaths(
        root=root,
        slug=slug,
        script_dir=root / "script",
        metadata_dir=root / "metadata",
        thumbnail_dir=root / "thumbnail",
        notes_dir=root / "notes",
        raw_clips_dir=root / "clips" / "raw",
        approved_clips_dir=root / "clips" / "approved",
        voiceover_dir=root / "voiceover",
        exports_dir=root / "exports",
        drafts_dir=root / "_drafts",
        assets_dir=root / "assets",
        scorecards_dir=root / "assets" / "scorecards",
        screenshots_dir=root / "assets" / "screenshots",
        timeline_dir=root / "timeline",
    )

    if create:
        for directory in (
            paths.script_dir,
            paths.metadata_dir,
            paths.thumbnail_dir,
            paths.notes_dir,
            paths.raw_clips_dir,
            paths.approved_clips_dir,
            paths.voiceover_dir,
            paths.exports_dir,
            paths.scorecards_dir,
            paths.screenshots_dir,
            paths.timeline_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    return paths


def latest_script(project: ProjectPaths | None, fallback_dir: Path) -> Path | None:
    if project:
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
    project.requirements_path.write_text(
        f"# Requirements: {topic}\n\n"
        "## Workflow\n"
        "1. Script and metadata are generated before clip gathering.\n"
        "2. Clips are gathered from script cues, then manually approved.\n"
        "3. Voiceover must complete naturally; never cut mid-sentence.\n"
        "4. Final export lives in this package's `exports/` folder.\n\n"
        "## Visual Rules\n"
        "- Use real game footage, relevant interviews, and relevant training/workout clips.\n"
        "- Use official scorecards, standings, rankings, and stat screenshots only when they support the audio.\n"
        "- Reject gameplay, simulations, fan hosts, podcast panels, subscribe/like overlays, creator title cards, and unrelated faces.\n"
        "- Avoid visible watermarks by rejecting the clip or cropping/zooming when the shot still works.\n"
        "- Keep edits minimal: hard cuts, light music under voiceover, no tacky CTA graphics.\n\n"
        "## Final Checks\n"
        "- Full audio completed.\n"
        "- No b-roll looping.\n"
        "- No abrupt ending.\n"
        "- No adjacent same-source clips when avoidable.\n",
        encoding="utf-8",
    )
