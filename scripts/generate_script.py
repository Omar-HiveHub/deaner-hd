"""
generate_script.py — Ready-to-Record Script Generator
======================================================
Full workflow:
  1. Accept a topic (and optional hook/type) as CLI input
     OR read the most recent approved idea from pipeline/ideas/
  2. Load DEAN.md and reference files as context
  3. Load 5 sample transcripts from voice/transcripts/ (sorted by view count)
     as voice examples — type-matched to the video content type
  4. Call Claude Sonnet via claude_client.generate_script(), which returns a
     complete voiceover-ready prose script in Dean's exact speaking voice
     with precise [CLIP:], [INTERVIEW:], and [GRAPHIC:] gather cues
  5. Save the script to pipeline/scripted/YYYY-MM-DD-[slug].md

The output is a full script Dean can read directly into a microphone — not
bullet points or a structural outline. It should sound like one of his actual
transcripts: conversational run-ons, "and/but/I mean" chains, "I think/I feel"
before opinions, "man" as emphasis, and his locked 5-step sign-off.

Run:
    python generate_script.py --topic "Nobody saw what happened to Bedard in Game 1"
    python generate_script.py --topic "..." --type incident
    python generate_script.py --topic "Gavin McKenna 2026 Draft" --type biography
    python generate_script.py --topic "..." --hook "They did it again."
    python generate_script.py --from-ideas   # picks top idea from latest ideas file
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

IDEAS_DIR      = _PROJECT_ROOT / "pipeline" / "ideas"
SCRIPTED_DIR   = _PROJECT_ROOT / "pipeline" / "scripted"
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    return project_slugify(text)


def load_top_idea_from_latest_file() -> tuple[str, str]:
    """
    Find the most recent ideas file in pipeline/ideas/ and extract
    the first (top-ranked) topic and its hook line.

    Returns:
        Tuple of (topic_string, hook_string).
        Returns ("", "") if no ideas file found or parsing fails.
    """
    try:
        ideas_files = sorted(IDEAS_DIR.glob("*.md"), reverse=True)
        if not ideas_files:
            print("[generate_script] No ideas files found in pipeline/ideas/")
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


def save_script(script_markdown: str, topic: str, topic_type: str, project=None) -> Path:
    """
    Save the generated script to pipeline/scripted/YYYY-MM-DD-[slug].md.

    Prepends a header with date, topic type, and word count estimate.
    Returns the path to the saved file.
    """
    slug = slugify(topic)
    if project:
        write_default_requirements(project, topic)
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
        f"_Generated: {TODAY} | Type: {topic_type} | ~{word_count} words spoken_\n\n"
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
            "Generate a complete ready-to-record voiceover script in Dean's exact voice. "
            "Output is full prose — not bullet points. Dean reads it directly into the mic."
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
        help="Auto-pick the top idea from the latest pipeline/ideas/ file"
    )
    parser.add_argument(
        "--project",
        type=str,
        default="",
        help="Optional project slug/path. Saves to pipeline/projects/YYYY-MM-DD-slug/script/."
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

    print(f"[generate_script] Generating script for: {topic}")
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
        script = generate_script(cue_context, hook=hook, topic_type=topic_type)
    except Exception as e:
        print(f"[generate_script] Claude API error: {e}")
        return

    output_path = save_script(script, topic, topic_type, project=project)
    print(f"[generate_script] Done. Check {output_path.parent}/ for your script.")


if __name__ == "__main__":
    main()
