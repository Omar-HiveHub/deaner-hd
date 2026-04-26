"""
generate_script.py — Ready-to-Record Script Generator
======================================================
Full workflow:
  1. Accept a topic (and optional hook/type) as CLI input
     OR read the most recent approved idea from pipeline/ideas/
  2. Scan clips/approved/ — load all approved clip filenames and their
     sidecar metadata JSON files (written by gather_clips.py)
  3. Load DEAN.md and reference files as context
  4. Load 5 sample transcripts from voice/transcripts/ (sorted by view count)
     as voice examples — type-matched to the video content type
  5. Call Claude Sonnet via claude_client.generate_script(), which returns a
     complete voiceover-ready prose script in Dean's exact speaking voice
  6. Save the script to pipeline/scripted/YYYY-MM-DD-[slug].md

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
import json
import re
from pathlib import Path
from dotenv import load_dotenv

from utils.claude_client import generate_script, load_context_from_dean_md

# ---------------------------------------------------------------------------
# Config and paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

IDEAS_DIR      = _PROJECT_ROOT / "pipeline" / "ideas"
SCRIPTED_DIR   = _PROJECT_ROOT / "pipeline" / "scripted"
APPROVED_CLIPS_DIR = _PROJECT_ROOT / "clips" / "approved"
TODAY = datetime.date.today().isoformat()

CLIP_EXTENSIONS = {".mp4", ".mov", ".mkv"}


# ---------------------------------------------------------------------------
# Approved clip loading
# ---------------------------------------------------------------------------

def load_approved_clips() -> list[dict]:
    """
    Scan clips/approved/ and return a list of clip info dicts.

    For each MP4/MOV/MKV file found, attempts to load the sidecar JSON
    written by gather_clips.py (same stem, .json extension). If no JSON
    exists the clip is still included with just its filename.

    Returns:
        List of dicts, each with at minimum:
          { "filename": str }
        Plus any fields from the sidecar JSON if present:
          { source_url, channel_name, timestamp_start, timestamp_end,
            topic, downloaded_at }
        Returns an empty list if clips/approved/ is empty or doesn't exist.
    """
    if not APPROVED_CLIPS_DIR.exists():
        return []

    clips = []
    for clip_file in sorted(APPROVED_CLIPS_DIR.iterdir()):
        if clip_file.suffix.lower() not in CLIP_EXTENSIONS:
            continue

        clip_info = {"filename": clip_file.name}

        metadata_path = clip_file.with_suffix(".json")
        if metadata_path.exists():
            try:
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                clip_info.update(meta)
            except Exception as e:
                print(f"[generate_script] Warning: could not read {metadata_path.name}: {e}")

        clips.append(clip_info)

    return clips


def format_clips_for_prompt(clips: list[dict]) -> str:
    """
    Format the approved clip list into a readable block for the Claude prompt.
    Lets Claude know exactly which footage is available so [CLIP:] markers
    can reference real files.
    """
    if not clips:
        return "No approved clips found in clips/approved/. Script clip cues will be descriptive placeholders."

    lines = ["Approved clips available in clips/approved/:"]
    for i, clip in enumerate(clips, 1):
        filename = clip.get("filename", "unknown")
        channel  = clip.get("channel_name", "unknown source")
        t_start  = clip.get("timestamp_start", "?")
        t_end    = clip.get("timestamp_end", "?")
        topic    = clip.get("topic", "")

        line = f"  {i}. {filename} — from {channel}"
        if t_start != "?" and t_end != "?":
            line += f" [{t_start}s–{t_end}s]"
        if topic:
            line += f" | topic: {topic}"
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:60].strip("-")


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


def save_script(script_markdown: str, topic: str, topic_type: str) -> Path:
    """
    Save the generated script to pipeline/scripted/YYYY-MM-DD-[slug].md.

    Prepends a header with date, topic type, and word count estimate.
    Returns the path to the saved file.
    """
    SCRIPTED_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)
    output_path = SCRIPTED_DIR / f"{TODAY}-{slug}.md"

    # Estimate word count (strip production markers for the count)
    spoken_text = re.sub(r"\[(?:CLIP|SFX|VERIFY)[^\]]*\]", "", script_markdown)
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

    # Load approved clips
    clips = load_approved_clips()
    if not clips:
        print("[generate_script] Warning: no approved clips found in clips/approved/.")
        print("                   Run gather_clips.py first, then move keepers to clips/approved/.")
        print("                   Continuing — script will use descriptive [CLIP:] placeholders.")
    else:
        print(f"[generate_script] Found {len(clips)} approved clip(s).")

    clips_context = format_clips_for_prompt(clips)
    topic_with_clips = f"{topic}\n\n{clips_context}"

    try:
        script = generate_script(topic_with_clips, hook=hook, topic_type=topic_type)
    except Exception as e:
        print(f"[generate_script] Claude API error: {e}")
        return

    save_script(script, topic, topic_type)
    print("[generate_script] Done. Check pipeline/scripted/ for your script.")


if __name__ == "__main__":
    main()
