"""
generate_shorts.py — Automated YouTube Shorts Pipeline
=======================================================
Full workflow (4 steps):

  STEP 1 — Moment detection (Gemini 2.5 Flash)
    Send the finished long-form video to Gemini. Ask it to identify 3–6
    moments under 30 seconds each that work as standalone Shorts. Criteria:
    strong opinions, surprising stats, emotional peaks, hooks within 3 seconds.
    Returns JSON: [{ start_seconds, end_seconds, reason }]

  STEP 2 — Clip and reframe (FFmpeg)
    For each detected moment:
      - Cut the segment using FFmpeg's -ss/-to flags
      - Reframe 16:9 source to 9:16 (1080x1920) using the blur-background method:
          a. Scale source to fill width (1080px wide)
          b. Create a blurred, vertically stretched version as the background
          c. Overlay the original (letterboxed) centered on top
      - Output: [title]-short-[n]-raw.mp4

  STEP 3 — Subtitles (Whisper + FFmpeg)
    For each reframed clip:
      - Transcribe with Whisper at word-level timestamps (word_timestamps=True)
      - Generate an ASS subtitle file:
          - Word-by-word highlight style (each word appears individually)
          - Bold white text, black drop shadow
          - Font size 14 (ASS font points — renders large on mobile)
          - Centered horizontally, positioned 20% from the bottom
      - Burn subtitles into video via FFmpeg: -vf "subtitles=file.ass"
      - Output: [title]-short-[n].mp4

  STEP 4 — Save output
    Save each finished Short to outputs/shorts/ as [title]-short-[n].mp4.
    Save a sidecar metadata JSON:
      { moment_reason, start_seconds, end_seconds, suggested_title }

REVIEW_MODE:
    When REVIEW_MODE = True (default), the script pauses after Step 1 and
    prints the proposed clip list. The user must type 'y' to proceed or
    edit the moments before continuing.

Run:
    python generate_shorts.py --video outputs/long-form/2026-04-04-video.mp4
    python generate_shorts.py --video outputs/long-form/2026-04-04-video.mp4 --title "canucks-breakdown"
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Set to True to pause after moment detection and require manual approval
REVIEW_MODE = True

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

SHORTS_OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "shorts"

# Whisper model size — "base" is fast and good enough for word-level timing.
# Use "small" or "medium" for higher accuracy.
WHISPER_MODEL_SIZE = "base"

# Output dimensions
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


def _find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for cand in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(cand):
            return cand
    raise EnvironmentError(f"{name} not found. Re-run setup.command.")


FFMPEG = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")
os.environ["PATH"] = str(Path(FFMPEG).parent) + os.pathsep + os.environ.get("PATH", "")


def get_duration(path: Path) -> float:
    result = subprocess.run(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Step 1 — Moment Detection
# ---------------------------------------------------------------------------

def detect_short_moments(video_path: Path) -> list[dict]:
    """
    Send the video to Gemini 2.5 Flash and get back a list of Short-worthy
    moments as structured JSON.

    Args:
        video_path: Path to the finished long-form MP4.

    Returns:
        List of moment dicts: [{ start_seconds, end_seconds, reason }]

    TODO:
        - Call detect_moments(str(video_path)) from gemini_client
        - Validate each dict has start_seconds, end_seconds, reason
        - Validate end_seconds > start_seconds
        - Validate duration <= 30 seconds per clip
        - Return validated list
    """
    print(f"[generate_shorts] Sending video to Gemini for moment detection...")
    try:
        from utils.gemini_client import detect_moments
        moments = detect_moments(str(video_path))
        return validate_moments(moments, get_duration(video_path))
    except Exception as e:
        print(f"[generate_shorts] Moment detection error: {e}")
        raise


def validate_moments(moments: list[dict], video_duration: float) -> list[dict]:
    validated = []
    for moment in moments:
        try:
            start = max(0.0, float(moment["start_seconds"]))
            end = min(video_duration, float(moment["end_seconds"]))
            if end <= start:
                continue
            if end - start > 34:
                end = start + 34
            if end - start < 12:
                continue
            validated.append({
                "start_seconds": round(start, 2),
                "end_seconds": round(end, 2),
                "reason": moment.get("reason", "Strong standalone moment"),
            })
        except Exception:
            continue
    return validated


def fallback_moments(video_path: Path, count: int = 3) -> list[dict]:
    duration = get_duration(video_path)
    count = max(1, min(count, 3))
    clip_len = min(30.0, max(18.0, duration / (count + 2)))
    anchors = [0.14, 0.46, 0.74][:count]
    moments = []
    for i, anchor in enumerate(anchors, 1):
        center = duration * anchor
        start = max(0.0, min(duration - clip_len, center - clip_len / 2))
        end = min(duration, start + clip_len)
        moments.append({
            "start_seconds": round(start, 2),
            "end_seconds": round(end, 2),
            "reason": f"Local fallback moment #{i}; review for hook strength before upload.",
        })
    return moments


def review_moments(moments: list[dict]) -> list[dict]:
    """
    If REVIEW_MODE is True, print proposed moments and wait for user approval.

    User can type 'y' to accept all, or enter comma-separated indices to
    keep only specific moments (e.g. "1,3,4" to keep moments 1, 3, and 4).

    Args:
        moments: List of moment dicts from detect_short_moments().

    Returns:
        Approved (possibly filtered) list of moments.
    """
    if not REVIEW_MODE:
        return moments

    print("\n" + "=" * 60)
    print("REVIEW MODE — Proposed Shorts:")
    print("=" * 60)
    for i, m in enumerate(moments, 1):
        duration = m["end_seconds"] - m["start_seconds"]
        print(f"\n  [{i}] {m['start_seconds']}s – {m['end_seconds']}s ({duration:.0f}s)")
        print(f"       Reason: {m['reason']}")
    print("\n" + "=" * 60)

    choice = input("\nApprove all? [y] or enter clip numbers to keep (e.g. 1,3): ").strip().lower()

    if choice == "y" or choice == "":
        print("[generate_shorts] All moments approved.")
        return moments

    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        approved = [moments[i] for i in indices if 0 <= i < len(moments)]
        print(f"[generate_shorts] Keeping {len(approved)} moment(s).")
        return approved
    except (ValueError, IndexError):
        print("[generate_shorts] Invalid input — keeping all moments.")
        return moments


# ---------------------------------------------------------------------------
# Step 2 — Clip and Reframe
# ---------------------------------------------------------------------------

def cut_and_reframe_clip(
    source_path: Path,
    start_seconds: float,
    end_seconds: float,
    output_path: Path
):
    """
    Cut a segment from the source video and reframe it from 16:9 to 9:16
    using the blur-background method.

    Reframe method (FFmpeg filter_complex):
      1. Scale source to 1080px wide (letterboxed, preserving aspect ratio)
      2. Create a blurred background: scale source to fill 1080x1920,
         crop to fit, apply boxblur
      3. Overlay letterboxed source centered on the blurred background
      4. Output: 1080x1920

    Args:
        source_path:   Path to the source long-form MP4.
        start_seconds: Clip start time in seconds.
        end_seconds:   Clip end time in seconds.
        output_path:   Where to save the reframed clip.

    TODO:
        - Build FFmpeg filter_complex string:
            [0:v]scale=1080:-2[fg];
            [0:v]scale=1080:1920:force_original_aspect_ratio=increase,
                  crop=1080:1920,boxblur=20:5[bg];
            [bg][fg]overlay=(W-w)/2:(H-h)/2[out]
        - Run via subprocess:
            ffmpeg -ss start -to end -i source
                   -filter_complex "..." -map "[out]" -map 0:a
                   -c:v libx264 -c:a aac output_path
        - Check returncode — raise on failure
    """
    print(f"  [reframe] {start_seconds}s–{end_seconds}s → {output_path.name}")

    filter_complex = (
        "[0:v]scale=1080:-2[fg];"
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:5[bg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
    )

    cmd = [
        FFMPEG, "-y",
        "-ss", str(start_seconds),
        "-to", str(end_seconds),
        "-i", str(source_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "medium",
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[generate_shorts] FFmpeg reframe error:\n{result.stderr}")
            raise RuntimeError(f"FFmpeg failed with code {result.returncode}")
    except FileNotFoundError:
        raise EnvironmentError(
            "FFmpeg not found. Install it from https://ffmpeg.org/download.html "
            "and ensure it's on your PATH."
        )


# ---------------------------------------------------------------------------
# Step 3 — Subtitles
# ---------------------------------------------------------------------------

def transcribe_clip(clip_path: Path) -> list[dict]:
    """
    Transcribe the audio of a clip using Whisper with word-level timestamps.

    Args:
        clip_path: Path to the reframed Short clip.

    Returns:
        List of word dicts: [{ word, start, end }]
        where start and end are timestamps in seconds.

    TODO:
        - Load Whisper model: whisper.load_model(WHISPER_MODEL_SIZE)
        - Transcribe: model.transcribe(str(clip_path), word_timestamps=True)
        - Flatten segments → words into a flat list of { word, start, end }
        - Return list
    """
    print(f"  [whisper] Transcribing {clip_path.name}...")
    try:
        import whisper
        model = whisper.load_model(WHISPER_MODEL_SIZE)
        result = model.transcribe(str(clip_path), word_timestamps=True, fp16=False, verbose=False)
        words: list[dict] = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                word_text = w.get("word", "").strip()
                start = w.get("start")
                end = w.get("end")
                if word_text and start is not None and end is not None and end > start:
                    words.append({"word": word_text, "start": float(start), "end": float(end)})
        return words
    except Exception as e:
        print(f"[generate_shorts] Whisper error: {e}")
        raise


def generate_ass_subtitles(words: list[dict], output_path: Path):
    """
    Write an ASS subtitle file from word-level timestamps.

    Subtitle style:
      - Short phrase chunks, not tacky word-by-word spam
      - Bold white text with black drop shadow (outline)
      - Large mobile-readable text
      - Centered horizontally, 20% from the bottom of the frame
      - Margin from bottom: 1920 * 0.20 = 384px

    ASS format reference:
      [V4+ Styles]: Name, Fontname, Fontsize, PrimaryColour, OutlineColour,
                    Bold, Italic, Alignment, MarginV, Outline, Shadow
      [Events]: Dialogue: start,end,Style,Text

    Args:
        words:       List of { word, start, end } dicts from transcribe_clip().
        output_path: Where to save the .ass file.

    TODO:
        - Write ASS header with style definition
        - For each word, write a Dialogue line with:
            - Start/End formatted as H:MM:SS.cs (centiseconds)
            - Text = the word (optionally {\b1} bold tag)
        - Write file to output_path
    """
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,70,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def seconds_to_ass_time(s: float) -> str:
        """Convert seconds to ASS time format H:MM:SS.cs"""
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"

    lines = [ass_header]
    for chunk in _subtitle_chunks(words):
        start = seconds_to_ass_time(chunk["start"])
        end = seconds_to_ass_time(chunk["end"])
        text = chunk["text"].strip()
        if text:
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\b1}}{text}")

    try:
        output_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print(f"[generate_shorts] Error writing ASS file: {e}")
        raise


def burn_subtitles(clip_path: Path, ass_path: Path, output_path: Path):
    """
    Burn the ASS subtitle file into the video using FFmpeg.

    Args:
        clip_path:   Path to the reframed clip (no subtitles).
        ass_path:    Path to the .ass subtitle file.
        output_path: Where to save the final clip with burned-in subtitles.

    TODO:
        - Run: ffmpeg -i clip_path -vf "subtitles=ass_path" -c:a copy output_path
        - Check returncode
    """
    print(f"  [subtitles] Burning subtitles into {output_path.name}...")
    subtitle_filter = f"subtitles=filename='{ass_path.name}'"
    cmd = [
        FFMPEG, "-y",
        "-i", str(clip_path),
        "-vf", subtitle_filter,
        "-c:a", "copy",
        str(output_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ass_path.parent))
        if result.returncode != 0:
            print(f"[generate_shorts] FFmpeg subtitle burn error:\n{result.stderr}")
            raise RuntimeError(f"FFmpeg failed with code {result.returncode}")
    except FileNotFoundError:
        raise EnvironmentError("FFmpeg not found. Install from https://ffmpeg.org/download.html")


def _subtitle_chunks(words: list[dict]) -> list[dict]:
    chunks = []
    current = []
    for word in words:
        current.append(word)
        text = " ".join(w["word"].strip() for w in current)
        duration = current[-1]["end"] - current[0]["start"]
        if len(current) >= 5 or duration >= 2.2 or len(text) >= 34:
            chunks.append({
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": _wrap_subtitle_text(text),
            })
            current = []
    if current:
        text = " ".join(w["word"].strip() for w in current)
        chunks.append({
            "start": current[0]["start"],
            "end": current[-1]["end"],
            "text": _wrap_subtitle_text(text),
        })
    return chunks


def _wrap_subtitle_text(text: str) -> str:
    clean = text.replace("{", "").replace("}", "").upper()
    words = clean.split()
    if len(words) <= 3:
        return clean
    midpoint = math.ceil(len(words) / 2)
    return " ".join(words[:midpoint]) + r"\N" + " ".join(words[midpoint:])


# ---------------------------------------------------------------------------
# Step 4 — Output and metadata
# ---------------------------------------------------------------------------

def save_short_metadata(output_path: Path, moment: dict, n: int, title: str):
    """
    Save a sidecar JSON file with metadata for each Short.

    Args:
        output_path: Path to the final .mp4 Short.
        moment:      The moment dict from detect_short_moments().
        n:           The Short's index number (1-based).
        title:       The video title slug.

    TODO:
        - Build metadata dict: moment_reason, start_seconds, end_seconds,
          suggested_title, duration_seconds, generated_at
        - Write to output_path.with_suffix(".json")
    """
    metadata = {
        "moment_reason": moment.get("reason", ""),
        "start_seconds": moment.get("start_seconds"),
        "end_seconds": moment.get("end_seconds"),
        "duration_seconds": moment.get("end_seconds", 0) - moment.get("start_seconds", 0),
        "suggested_title": f"{title} — Short #{n}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = output_path.with_suffix(".json")
    try:
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[generate_shorts] Error writing metadata: {e}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_short(
    source_video: Path,
    moment: dict,
    n: int,
    title: str
):
    """
    Run the full 4-step pipeline for a single Short moment.

    Args:
        source_video: Path to the finished long-form MP4.
        moment:       { start_seconds, end_seconds, reason }
        n:            Short index (1-based), used in filename.
        title:        Video title slug.
    """
    SHORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start = moment["start_seconds"]
    end = moment["end_seconds"]
    base_name = f"{title}-short-{n}"

    # Intermediate files
    reframed_path = SHORTS_OUTPUT_DIR / f"{base_name}-reframed.mp4"
    ass_path = SHORTS_OUTPUT_DIR / f"{base_name}.ass"
    final_path = SHORTS_OUTPUT_DIR / f"{base_name}.mp4"

    # Step 2 — Cut and reframe
    cut_and_reframe_clip(source_video, start, end, reframed_path)

    # Step 3 — Transcribe, generate subtitles, burn in
    try:
        words = transcribe_clip(reframed_path)
        generate_ass_subtitles(words, ass_path)
        burn_subtitles(reframed_path, ass_path, final_path)
        # Clean up intermediate files
        reframed_path.unlink(missing_ok=True)
        ass_path.unlink(missing_ok=True)
    except NotImplementedError:
        print(f"  [generate_shorts] Whisper not implemented — skipping subtitles")
        reframed_path.rename(final_path)

    # Step 4 — Save metadata
    save_short_metadata(final_path, moment, n, title)
    print(f"  [generate_shorts] Short {n} saved: {final_path.name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Automatically cut and format YouTube Shorts from a finished video."
    )
    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="Path to the finished long-form MP4 (e.g. outputs/long-form/2026-04-04-video.mp4)"
    )
    parser.add_argument(
        "--title",
        type=str,
        default="video",
        help="Short title slug used in output filenames (default: 'video')"
    )
    parser.add_argument(
        "--moments",
        default="",
        help="Optional JSON list of moments; skips Gemini detection."
    )
    parser.add_argument(
        "--auto-local",
        action="store_true",
        help="Use local fallback moment picking instead of Gemini."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Approve detected/fallback moments without interactive review."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of fallback Shorts to create (default: 3)."
    )
    args = parser.parse_args()

    source_video = Path(args.video)
    if not source_video.exists():
        print(f"[generate_shorts] Video not found: {source_video}")
        sys.exit(1)

    if args.moments:
        moments = validate_moments(json.loads(args.moments), get_duration(source_video))
    elif args.auto_local:
        moments = fallback_moments(source_video, count=args.count)
    else:
        try:
            moments = detect_short_moments(source_video)
        except Exception as e:
            print(f"[generate_shorts] Gemini unavailable; using local fallback. ({e})")
            moments = fallback_moments(source_video, count=args.count)

    # Review gate
    approved_moments = moments if args.yes else review_moments(moments)
    if not approved_moments:
        print("[generate_shorts] No moments approved. Exiting.")
        sys.exit(0)

    print(f"\n[generate_shorts] Processing {len(approved_moments)} Short(s)...")

    # Steps 2–4 for each approved moment
    for i, moment in enumerate(approved_moments, 1):
        try:
            process_short(source_video, moment, i, args.title)
        except Exception as e:
            print(f"[generate_shorts] Error processing Short {i}: {e}")
            continue

    print(f"\n[generate_shorts] Done. Shorts saved to {SHORTS_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
