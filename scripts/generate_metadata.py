"""
generate_metadata.py — YouTube Metadata Generator
===================================================
Generates titles, description, and tags in Dean's voice for a finished video.
Uses Claude Haiku 4.5 (fast + cheap, same voice family as the script).

Workflow:
  1. Accept a script, transcript, or project folder.
  2. Locate matching transcript in 03_Reference/transcripts/ or a project outline/script.
  3. Pass the script/transcript to claude_client.generate_metadata()
  4. Save output as `03_metadata.txt` in the project package.

Run:
    python3 scripts/dean.py metadata 2026-05-29-topic-slug

Output:
    02_Projects/2026-05-29-topic-slug/03_metadata.txt
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from utils.projects import latest_script, resolve_project, write_default_requirements

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")


def get_video_summary(video_path: Path) -> str:
    """
    Find the best content summary for the given video, in priority order:
      1. Matching transcript at 03_Reference/transcripts/[stem].txt
      2. Matching reference script content
      3. Empty string (Claude falls back to filename hint)
    """
    transcripts_dir = _PROJECT_ROOT / "03_Reference" / "transcripts"
    legacy_transcripts_dir = _PROJECT_ROOT / "03_Reference" / "transcripts"
    transcript_path = transcripts_dir / f"{video_path.stem}.txt"
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")[:3000]
    matches = list(transcripts_dir.rglob(f"{video_path.stem}.txt"))
    if matches:
        return matches[0].read_text(encoding="utf-8")[:3000]
    if legacy_transcripts_dir.exists():
        legacy_matches = list(legacy_transcripts_dir.rglob(f"{video_path.stem}.txt"))
        if legacy_matches:
            return legacy_matches[0].read_text(encoding="utf-8")[:3000]

    scripted_dir = _PROJECT_ROOT / "03_Reference" / "past-scripts"
    if scripted_dir.exists():
        stem_tail = video_path.stem.split("-", 3)[-1] if "-" in video_path.stem else video_path.stem
        for outline_file in scripted_dir.glob("*.md"):
            if stem_tail.lower() in outline_file.stem.lower():
                return outline_file.read_text(encoding="utf-8")[:3000]

    return ""


def save_metadata(metadata: str, target_path: Path, project=None) -> Path:
    if project:
        write_default_requirements(project)
        output_path = project.metadata_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = target_path.parent / f"{target_path.stem}-metadata.txt"
    header = (
        f"# Metadata for: {target_path.name}\n"
        f"# Generated: {datetime.now().isoformat()}\n"
        f"# Model: Claude Haiku 4.5\n\n"
    )
    output_path.write_text(header + metadata, encoding="utf-8")
    print(f"[generate_metadata] Saved to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube titles, description, and tags for a finished video."
    )
    parser.add_argument("--video", type=str, default="", help="Path to the finished long-form MP4")
    parser.add_argument(
        "--script", type=str, default=None,
        help="Optional path to a script/transcript. Can be used before video render."
    )
    parser.add_argument(
        "--project", type=str, default="",
        help="Optional project slug/path. Reads project script and saves to project metadata folder."
    )
    args = parser.parse_args()
    project = resolve_project(args.project, create=True)

    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"[generate_metadata] Script not found: {script_path}")
            sys.exit(1)
        summary = script_path.read_text(encoding="utf-8")[:3000]
        target_path = script_path
    elif project:
        script_path = latest_script(project, _PROJECT_ROOT / "03_Reference" / "past-scripts")
        if not script_path or not script_path.exists():
            print(f"[generate_metadata] No project script found in {project.script_dir}")
            sys.exit(1)
        summary = script_path.read_text(encoding="utf-8")[:3000]
        target_path = script_path
    else:
        if not args.video:
            print("[generate_metadata] Pass --script before render, or --video after render.")
            sys.exit(1)
        video_path = Path(args.video)
        if not video_path.exists():
            print(f"[generate_metadata] Video not found: {video_path}")
            sys.exit(1)
        summary = get_video_summary(video_path)
        target_path = video_path
        if not summary:
            print(f"[generate_metadata] No transcript or script found — using filename hint only.")

    print(f"[generate_metadata] Generating metadata via Claude Haiku 4.5...")
    from utils.claude_client import generate_metadata as claude_generate_metadata
    metadata = claude_generate_metadata(summary, video_filename=target_path.name)
    output_path = save_metadata(metadata, target_path, project=project)
    print(f"[generate_metadata] Done. Open {output_path} to copy-paste into YouTube Studio.")


if __name__ == "__main__":
    main()
