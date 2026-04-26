"""
generate_metadata.py — YouTube Metadata Generator
===================================================
Generates titles, description, and tags in Dean's voice for a finished video.
Uses Claude Haiku 4.5 (fast + cheap, same voice family as the script).

Workflow:
  1. Accept a path to a finished video in outputs/long-form/
  2. Locate matching transcript (voice/transcripts/) or script (pipeline/scripted/)
  3. Pass the script/transcript to claude_client.generate_metadata()
  4. Save output as .txt next to the video — paste-ready for YouTube Studio

Run:
    python generate_metadata.py --video outputs/long-form/2026-04-26-stenberg.mp4

Output:
    outputs/long-form/2026-04-26-stenberg-metadata.txt
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from utils.claude_client import generate_metadata as claude_generate_metadata

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")


def get_video_summary(video_path: Path) -> str:
    """
    Find the best content summary for the given video, in priority order:
      1. Matching transcript at voice/transcripts/[stem].txt
      2. Matching script at pipeline/scripted/*[stem]*.md
      3. Empty string (Claude falls back to filename hint)
    """
    transcripts_dir = _PROJECT_ROOT / "voice" / "transcripts"
    transcript_path = transcripts_dir / f"{video_path.stem}.txt"
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")[:3000]

    scripted_dir = _PROJECT_ROOT / "pipeline" / "scripted"
    if scripted_dir.exists():
        stem_tail = video_path.stem.split("-", 3)[-1] if "-" in video_path.stem else video_path.stem
        for outline_file in scripted_dir.glob("*.md"):
            if stem_tail.lower() in outline_file.stem.lower():
                return outline_file.read_text(encoding="utf-8")[:3000]

    return ""


def save_metadata(metadata: str, video_path: Path) -> Path:
    output_path = video_path.parent / f"{video_path.stem}-metadata.txt"
    header = (
        f"# Metadata for: {video_path.name}\n"
        f"# Generated: {datetime.utcnow().isoformat()}\n"
        f"# Model: Claude Haiku 4.5\n\n"
    )
    output_path.write_text(header + metadata, encoding="utf-8")
    print(f"[generate_metadata] Saved to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube titles, description, and tags for a finished video."
    )
    parser.add_argument(
        "--video", type=str, required=True,
        help="Path to the finished long-form MP4 in outputs/long-form/"
    )
    parser.add_argument(
        "--script", type=str, default=None,
        help="Optional path to a script or transcript file to use as content. "
             "If omitted, auto-discovers from voice/transcripts/ or pipeline/scripted/."
    )
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"[generate_metadata] Video not found: {video_path}")
        sys.exit(1)

    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"[generate_metadata] Script not found: {script_path}")
            sys.exit(1)
        summary = script_path.read_text(encoding="utf-8")[:3000]
    else:
        summary = get_video_summary(video_path)
        if not summary:
            print(f"[generate_metadata] No transcript or script found — using filename hint only.")

    print(f"[generate_metadata] Generating metadata via Claude Haiku 4.5...")
    metadata = claude_generate_metadata(summary, video_filename=video_path.name)
    output_path = save_metadata(metadata, video_path)
    print(f"[generate_metadata] Done. Open {output_path} to copy-paste into YouTube Studio.")


if __name__ == "__main__":
    main()
