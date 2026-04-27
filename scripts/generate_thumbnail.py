"""
generate_thumbnail.py — YouTube Thumbnail Brief Generator
==========================================================
Closes Dean's named pain point: "low CTR from poor thumbnails."

Generates a concrete, Canva-ready thumbnail brief — which player(s), what
expression, the 1-3 word headline text, color palette, layout — that Dean (or
a designer) can execute in 5 minutes.

Uses Claude Opus 4.7. Dean can optionally drop reference thumbnails (his own
top performers, or competitor Hockey Psychology screenshots) into
references/thumbnails/ — if present, the script will pass them as vision input
so Opus can pattern-match concretely.

Run:
    python generate_thumbnail.py --video outputs/long-form/2026-04-26-stenberg.mp4
    python generate_thumbnail.py --script pipeline/scripted/stenberg-script.md

Output:
    Saved next to the video as [video-stem]-thumbnail-brief.txt
"""

import argparse
import base64
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from utils.projects import latest_script, resolve_project, write_default_requirements

import anthropic

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

import os
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_key_here":
    print("[generate_thumbnail] ANTHROPIC_API_KEY not set. See SETUP.md step 3.")
    sys.exit(1)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-opus-4-7"

REFERENCES_DIR = _PROJECT_ROOT / "references" / "thumbnails"

SYSTEM_PROMPT = """You are a YouTube thumbnail strategist for the DeanerHD hockey
commentary channel. Your job is to write a Canva-ready brief that produces a
high-CTR thumbnail Dean can execute in 5 minutes — no design experience required.

DeanerHD's winning thumbnail patterns (from videos that hit 60k–190k views):
  - Two players clearly visible, mid-emotion (intensity, shock, joy, anger)
  - Clear close-up faces — never zoomed-out arena wide shots
  - Bold 1-3 word headline overlay in SELECTIVE caps (one or two emotional words)
  - High-contrast background — usually dark blue or gradient, not arena ice
  - Player's team color as a secondary accent
  - Optional: a small visual cue that ties to the story (a goal red light,
    a glove down, a glance, a microphone)

What makes Dean's thumbnails LOSE:
  - Tiny zoomed-out players
  - Wall-of-text headlines (more than 4 words)
  - Generic NHL logos / news graphics
  - Three or more faces — clutter

Reference comp: Hockey Psychology (his benchmark) — clean two-person composition,
bold yellow/white text, dark gradient background, ~80% face/expression dominance.
"""


def load_reference_images() -> list[dict]:
    """Load up to 3 reference thumbnail images from references/thumbnails/, base64 encoded."""
    if not REFERENCES_DIR.exists():
        return []
    images = []
    for path in sorted(REFERENCES_DIR.glob("*"))[:3]:
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        media_type = {
            ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp",
        }[path.suffix.lower()]
        try:
            data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
            images.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            })
        except Exception:
            continue
    return images


def generate_thumbnail_brief(script_text: str, video_filename: str = "") -> str:
    references = load_reference_images()

    user_content: list = []
    if references:
        user_content.append({
            "type": "text",
            "text": f"Reference thumbnails from Dean's top performers / competitors "
                    f"({len(references)} images). Pattern-match these for composition, "
                    f"text style, and color palette."
        })
        user_content.extend(references)

    script_excerpt = (script_text or "").strip()[:4000]
    user_content.append({
        "type": "text",
        "text": f"""Write a thumbnail brief for the following video.

Video filename: {video_filename or "(unnamed)"}

Script / transcript excerpt:
---
{script_excerpt}
---

Output the brief in this exact format:

## HEADLINE TEXT
1–3 words, max. Selective caps on the most emotional word.
Give 3 options ranked by likely CTR.

## SUBJECT
Who's in the frame? Be specific:
  - Primary face (player + team + emotion to capture)
  - Secondary face (if any) and how they relate (rival, GM, coach, target)
  - Camera angle: close-up / mid / shoulder

## VISUAL HOOK
The one detail that stops the scroll. (e.g., "red light behind Bedard's
shoulder", "Tkachuk's gloved hand mid-shove", "split frame: McKenna stat
vs scout face")

## BACKGROUND
Dark gradient base color (hex), accent color (hex tied to team), texture or
overlay if any.

## LAYOUT (left-to-right or grid)
Where exactly each element sits. Be concrete enough Dean can execute in Canva.

## ASSET CHECKLIST
Bullet list of images Dean needs to source (player headshot, team logo,
stat graphic). Include suggested search terms for Getty / NHL.com.

## DO-NOT-DO
2-3 bullets reminding what NOT to do — common failures for this kind of video.
"""
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def main():
    parser = argparse.ArgumentParser(description="Generate a thumbnail brief for a video.")
    parser.add_argument("--video", type=str, help="Path to finished long-form MP4")
    parser.add_argument("--script", type=str, help="Path to a script or transcript file")
    parser.add_argument("--project", type=str, default="", help="Optional project slug/path")
    args = parser.parse_args()

    project = resolve_project(args.project, create=True)

    if not args.video and not args.script and not project:
        print("Pass either --video, --script, or --project.")
        sys.exit(1)

    # Load script content
    script_text = ""
    output_dir = _PROJECT_ROOT / "outputs" / "long-form"
    output_stem = "thumbnail-brief"
    video_filename = ""

    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"Script not found: {script_path}")
            sys.exit(1)
        script_text = script_path.read_text(encoding="utf-8")
        output_stem = script_path.stem
    elif project:
        script_path = latest_script(project, _PROJECT_ROOT / "pipeline" / "scripted")
        if script_path and script_path.exists():
            script_text = script_path.read_text(encoding="utf-8")
            output_stem = project.slug

    if args.video:
        video_path = Path(args.video)
        if not video_path.exists():
            print(f"Video not found: {video_path}")
            sys.exit(1)
        video_filename = video_path.name
        output_dir = video_path.parent
        output_stem = video_path.stem
        # If no --script, try to auto-find one
        if not script_text:
            transcripts_dir = _PROJECT_ROOT / "voice" / "transcripts"
            transcript_path = transcripts_dir / f"{video_path.stem}.txt"
            if transcript_path.exists():
                script_text = transcript_path.read_text(encoding="utf-8")
            else:
                matches = list(transcripts_dir.rglob(f"{video_path.stem}.txt"))
                if matches:
                    script_text = matches[0].read_text(encoding="utf-8")
            if not script_text:
                scripted_dir = _PROJECT_ROOT / "pipeline" / "scripted"
                if scripted_dir.exists():
                    for f in sorted(scripted_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                        script_text = f.read_text(encoding="utf-8")
                        break

    print(f"[generate_thumbnail] Generating brief via Claude Opus 4.7...")
    brief = generate_thumbnail_brief(script_text, video_filename)

    if project:
        write_default_requirements(project, video_filename or output_stem)
        output_path = project.thumbnail_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = output_dir / f"{output_stem}-thumbnail-brief.txt"
    header = (
        f"# Thumbnail brief for: {video_filename or args.script}\n"
        f"# Generated: {datetime.utcnow().isoformat()}\n"
        f"# Model: Claude Opus 4.7\n\n"
    )
    output_path.write_text(header + brief, encoding="utf-8")
    print(f"[generate_thumbnail] Saved to {output_path}")


if __name__ == "__main__":
    main()
