"""
generate_script.py — Dean-Ready Outline / Script Generator
===========================================================
Full workflow:
  1. Accept a topic (and optional hook/type) as CLI input
     OR read the most recent approved idea from 01_Ideas/
  2. Load DEAN.md and reference files as context
  3. Load 5 sample transcripts from 03_Reference/transcripts/ (sorted by view count)
     as voice examples — type-matched to the video content type
  4. Call Claude via claude_client.generate_script(), which returns Dean's
     default recording outline (hooks, section beats, clip cues, CTA options)
     unless --format script is explicitly requested.
  5. Save the outline/script to the active project folder.

Default output matches the kickoff-call workflow: Dean reviews an outline,
clips are gathered from precise production cues, then Dean records naturally
from the beats. Full word-for-word scripts are still available for cases where
Omar/Dean explicitly asks for one.

Run:
    python3 generate_script.py --topic "Nobody saw what happened to Bedard in Game 1"
    python3 generate_script.py --topic "..." --type incident
    python3 generate_script.py --topic "Gavin McKenna 2026 Draft" --type biography
    python3 generate_script.py --topic "..." --format script
    python3 generate_script.py --from-ideas   # picks top idea from latest ideas file
"""

import argparse
import datetime
import re
from pathlib import Path
from dotenv import load_dotenv

from utils.claude_client import generate_script, load_context_from_dean_md
from utils.projects import resolve_project, slugify as project_slugify, write_default_requirements

# ---------------------------------------------------------------------------
# Config and paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

IDEAS_DIR      = _PROJECT_ROOT / "01_Ideas"
LEGACY_IDEAS_DIR = _PROJECT_ROOT / "01_Ideas"
SCRIPTED_DIR   = _PROJECT_ROOT / "03_Reference" / "past-scripts"
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    return project_slugify(text)


def load_top_idea_from_latest_file() -> tuple[str, str]:
    """
    Find the most recent ideas file in 01_Ideas/ and extract
    the first (top-ranked) topic and its hook line.

    Returns:
        Tuple of (topic_string, hook_string).
        Returns ("", "") if no ideas file found or parsing fails.
    """
    try:
        ideas_files = sorted(IDEAS_DIR.glob("*.md"), reverse=True)
        if not ideas_files and LEGACY_IDEAS_DIR.exists():
            ideas_files = sorted(LEGACY_IDEAS_DIR.glob("*.md"), reverse=True)
        if not ideas_files:
            print("[generate_script] No ideas files found in 01_Ideas/")
            return ("", "")
        latest = ideas_files[0]
        print(f"[generate_script] Loading top idea from {latest.name}")
        text = latest.read_text(encoding="utf-8")
        title_match = re.search(r"^\s*1\.\s+\*?\*?(.+?)\*?\*?\s*$", text, re.MULTILINE)
        topic = title_match.group(1).strip() if title_match else ""
        hook_match = re.search(r"[-–]\s*Hook:\s*[\"']?(.+?)[\"']?\s*$", text, re.MULTILINE | re.IGNORECASE)
        hook = hook_match.group(1).strip() if hook_match else ""
        return (topic, hook)
    except Exception as e:
        print(f"[generate_script] Error reading ideas file: {e}")
        return ("", "")


def save_script(script_markdown: str, topic: str, topic_type: str, output_format: str, project=None) -> Path:
    """
    Save the generated outline or script.

    Prepends a header with date, topic type, and word count estimate.
    Returns the path to the saved file.
    """
    slug = slugify(topic)
    if project:
        write_default_requirements(project, topic)
        if getattr(project, "simple_layout", False) and output_format == "script":
            output_path = project.root / "02_script.md"
        else:
            output_path = project.script_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        SCRIPTED_DIR.mkdir(parents=True, exist_ok=True)
        output_path = SCRIPTED_DIR / f"{TODAY}-{slug}.md"

    # Estimate word count (strip production markers for the count)
    spoken_text = re.sub(r"\[(?:CLIP|INTERVIEW|GRAPHIC|CARD|VERIFY)[^\]]*\]", "", script_markdown)
    word_count  = len(spoken_text.split())

    header = (
        f"# Script: {topic}\n"
        f"_Generated: {TODAY} | Type: {topic_type} | Format: {output_format} | ~{word_count} words spoken_\n\n"
        f"---\n\n"
    )
    try:
        output_path.write_text(header + script_markdown, encoding="utf-8")
        print(f"[generate_script] Script saved to {output_path}")
    except Exception as e:
        print(f"[generate_script] Error saving script: {e}")
        raise
    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate Dean's default recording outline, or a full script when explicitly requested."
        )
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="",
        help="Video topic or working title"
    )
    parser.add_argument(
        "--hook",
        type=str,
        default="",
        help="Optional opening hook line (overrides Claude's opener choice)"
    )
    parser.add_argument(
        "--type",
        choices=["auto", "incident", "biography"],
        default="auto",
        help=(
            "Video type for voice-matched example selection. "
            "'incident' loads fight/moment/drama/Leafs transcripts as examples. "
            "'biography' loads player-analysis transcripts. "
            "'auto' uses the top 5 by view count regardless of type (default)."
        ),
    )
    parser.add_argument(
        "--from-ideas",
        action="store_true",
        help="Auto-pick the top idea from the latest 01_Ideas/ file"
    )
    parser.add_argument(
        "--project",
        type=str,
        default="",
        help="Optional project slug/path. Saves to the project folder."
    )
    parser.add_argument(
        "--format",
        choices=["outline", "script"],
        default="outline",
        help="Default is Dean's preferred outline-first workflow. Use 'script' for word-for-word prose."
    )
    args = parser.parse_args()

    topic      = args.topic
    hook       = args.hook
    topic_type = args.type

    if args.from_ideas or not topic:
        topic, hook = load_top_idea_from_latest_file()
        if not topic:
            print("[generate_script] No topic found. Pass --topic or run fetch_ideas.py first.")
            return

    print(f"[generate_script] Generating {args.format} for: {topic}")
    print(f"[generate_script] Type: {topic_type}")
    if hook:
        print(f"[generate_script] Hook: {hook}")
    project = resolve_project(args.project, seed=topic, create=True)
    if project:
        print(f"[generate_script] Project: {project.root}")

    cue_context = (
        f"{topic}\n\n"
        "Workflow note: write the script before clips are gathered. Include precise "
        "[CLIP:], [INTERVIEW:], and [GRAPHIC:] cues that can be searched later. "
        "Each cue should name the player/team/event/source context clearly."
    )

    try:
        script = generate_script(cue_context, hook=hook, topic_type=topic_type, output_format=args.format)
    except Exception as e:
        print(f"[generate_script] Claude API error: {e}")
        return

    output_path = save_script(script, topic, topic_type, args.format, project=project)
    print(f"[generate_script] Done. Check {output_path.parent}/ for your {args.format}.")


if __name__ == "__main__":
    main()
