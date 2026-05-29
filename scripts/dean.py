#!/usr/bin/env python3
"""
Dean-facing wrapper for the simplified production kit.

This is the only command Dean should need. It creates simple project folders,
delegates useful generation steps to the existing scripts, and keeps final
editing out of the default promise.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from utils.projects import PROJECT_ROOT, resolve_project, slugify, write_default_requirements


PYTHON = sys.executable
SCRIPT_DIR = Path(__file__).resolve().parent
def _run(script_name: str, *args: str) -> None:
    subprocess.run([PYTHON, str(SCRIPT_DIR / script_name), *args], check=True)


def _project_topic(project_root: Path) -> str:
    name = project_root.name
    parts = name.split("-", 3)
    if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
        name = parts[3]
    return name.replace("-", " ")


def _write_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def create_project(topic: str) -> Path:
    slug = slugify(topic)
    root = PROJECT_ROOT / "02_Projects" / f"{dt.date.today().isoformat()}-{slug}"
    project = resolve_project(root, seed=topic, create=True)
    if not project:
        raise SystemExit("[dean] Could not create project.")

    write_default_requirements(project, topic)
    _write_if_missing(
        project.root / "01_outline.md",
        f"# Outline: {topic}\n\n"
        "## Hooks\n\n"
        "- \n\n"
        "## Section Beats\n\n"
        "1. \n\n"
        "## Clip Cues\n\n"
        "- [CLIP: ]\n\n"
        "## CTA Options\n\n"
        "- Let me know in the comments section below.\n",
    )
    _write_if_missing(
        project.root / "02_script.md",
        "# Optional Full Script\n\n"
        "Dean usually records from the outline. Use this only when a word-for-word script is requested.\n",
    )
    _write_if_missing(
        project.root / "03_metadata.txt",
        "# Metadata\n\nRun `python3 scripts/dean.py metadata <project>` after the outline is ready.\n",
    )
    _write_clip_cue_sheet(project.root)
    print(f"[dean] Created project: {project.root}")
    print("[dean] Next: python3 scripts/dean.py outline " + str(project.root))
    return project.root


def _write_clip_cue_sheet(project_root: Path) -> Path:
    project = resolve_project(project_root, create=False)
    raw = project.raw_clips_dir if project else project_root / "clips" / "raw"
    out_path = project_root / "04_clip_cue_sheet.csv"
    rows = []
    for sidecar in sorted(raw.glob("*.json")):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        rows.append(
            {
                "clip_file": sidecar.with_suffix(".mp4").name,
                "topic": data.get("topic", ""),
                "source_title": data.get("video_title", ""),
                "source_channel": data.get("channel_name", ""),
                "source_url": data.get("source_url", ""),
                "source_start": data.get("timestamp_start", ""),
                "source_end": data.get("timestamp_end", ""),
                "editor_notes": "",
            }
        )

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "clip_file",
                "topic",
                "source_title",
                "source_channel",
                "source_url",
                "source_start",
                "source_end",
                "editor_notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def package_project(project_arg: str) -> None:
    project = resolve_project(project_arg, create=False)
    if not project or not project.root.exists():
        raise SystemExit(f"[dean] Project not found: {project_arg}")
    cue_sheet = _write_clip_cue_sheet(project.root)
    raw_count = len(list(project.raw_clips_dir.glob("*.mp4")))
    status = project.root / "00_READ_ME.md"
    text = status.read_text(encoding="utf-8") if status.exists() else f"# Project: {_project_topic(project.root)}\n"
    summary = (
        "\n\n## Latest Package Check\n\n"
        f"- Raw clips: {raw_count}\n"
        f"- Clip folder: `clips/{project.root.name}/raw/`\n"
        f"- Clip cue sheet: `{cue_sheet.name}`\n"
        "- Final edit: manual in Dean's editor\n"
    )
    if "## Latest Package Check" in text:
        text = text.split("## Latest Package Check", 1)[0].rstrip() + summary
    else:
        text = text.rstrip() + summary
    status.write_text(text + "\n", encoding="utf-8")
    print(f"[dean] Package checked: {project.root}")
    print(f"[dean] Cue sheet: {cue_sheet}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple DeanerHD production wrapper.")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("ideas", help="Fetch source report/topic ideas into 01_Ideas.")

    new_parser = sub.add_parser("new", help="Create a simple project folder.")
    new_parser.add_argument("topic")

    outline_parser = sub.add_parser("outline", help="Generate a Dean-style outline.")
    outline_parser.add_argument("project")
    outline_parser.add_argument("--script", action="store_true", help="Generate a full script instead of an outline.")

    gather_parser = sub.add_parser("gather", help="Gather clips from project outline cues.")
    gather_parser.add_argument("project")
    gather_parser.add_argument("--section", default="", help="Only re-gather cues matching this section/cue phrase.")

    metadata_parser = sub.add_parser("metadata", help="Generate upload titles/description/tags.")
    metadata_parser.add_argument("project")

    package_parser = sub.add_parser("package", help="Refresh cue sheet and project status.")
    package_parser.add_argument("project")

    args = parser.parse_args()

    if args.action == "ideas":
        _run("fetch_ideas.py", "--sources-only")
    elif args.action == "new":
        create_project(args.topic)
    elif args.action == "outline":
        project = resolve_project(args.project, create=False)
        if not project or not project.root.exists():
            raise SystemExit(f"[dean] Project not found: {args.project}")
        fmt = "script" if args.script else "outline"
        _run("generate_script.py", "--topic", _project_topic(project.root), "--project", str(project.root), "--format", fmt)
    elif args.action == "gather":
        gather_args = ["--project", args.project, "--from-outline", "--auto", "--search-provider", "ytdlp"]
        if args.section:
            gather_args.extend(["--section", args.section])
        _run("gather_clips.py", *gather_args)
    elif args.action == "metadata":
        _run("generate_metadata.py", "--project", args.project)
    elif args.action == "package":
        package_project(args.project)


if __name__ == "__main__":
    main()
