"""
transcribe_channel.py — Fetch, transcribe, and save ALL long-form videos
from a YouTube channel without needing a YouTube Data API key.

Already-transcribed videos are skipped automatically — safe to re-run.

Usage:
    python transcribe_channel.py <channel_url>

Example:
    python transcribe_channel.py https://www.youtube.com/channel/UCmJOytiry5aHIKUMA9Ogf-g

Output:
    voice/transcripts/<YYYYMMDD>-<video-id>.txt  — one file per video

Fields in each file:
    TITLE, DESCRIPTION, DATE, VIEW COUNT, LIKE COUNT, COMMENT COUNT,
    VIDEO ID, URL, TRANSCRIPT
"""

import os
import ssl
import sys
import json
import re
import subprocess
import shutil
import tempfile
from pathlib import Path

# Fix macOS Python SSL cert verification issue
ssl._create_default_https_context = ssl._create_unverified_context

# Ensure Homebrew ffmpeg is on PATH (needed by both yt-dlp and Whisper)
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import whisper

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = _PROJECT_ROOT / "voice" / "transcripts"
SCRATCH_DIR     = _PROJECT_ROOT / "voice" / "_scratch"

# ffmpeg location (Homebrew on Apple Silicon)
FFMPEG_DIR = "/opt/homebrew/bin"

TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Skip helper
# ---------------------------------------------------------------------------

def _already_transcribed(video_id: str) -> bool:
    """Return True if a transcript for this video_id already exists in TRANSCRIPTS_DIR."""
    return bool(list(TRANSCRIPTS_DIR.rglob(f"*-{video_id}.txt")))


# ---------------------------------------------------------------------------
# Step 1 — Fetch video metadata (no API key needed)
# ---------------------------------------------------------------------------

def fetch_channel_videos(channel_url: str) -> list[dict]:
    """
    Use yt-dlp to pull metadata for ALL non-Short, non-live public videos on the channel.
    Returns a list of dicts: title, description, upload_date, video_id,
    view_count, like_count, comment_count, webpage_url, duration.
    """
    print(f"\n[1/3] Fetching channel metadata (this may take a minute for large channels)...")

    cmd = [
        "yt-dlp",
        "--dump-json",          # no --playlist-end limit — fetch entire channel
        "--no-warnings",
        "--quiet",
        channel_url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    videos = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue

        duration = d.get("duration") or 0
        is_live  = d.get("was_live") or d.get("is_live") or False

        # Skip YouTube Shorts (≤ 90 sec) and live streams
        if duration <= 90 or is_live:
            continue

        date_raw = d.get("upload_date", "")
        if re.match(r"^\d{8}$", date_raw):
            date_fmt = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
        else:
            date_fmt = date_raw

        videos.append({
            "video_id":      d.get("id", ""),
            "title":         d.get("title", "Unknown"),
            "description":   (d.get("description") or "").strip(),
            "upload_date":   date_fmt,
            "view_count":    d.get("view_count", "N/A"),
            "like_count":    d.get("like_count", "N/A"),
            "comment_count": d.get("comment_count", "N/A"),
            "webpage_url":   d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id','')}",
            "duration":      duration,
        })

    print(f"  Found {len(videos)} long-form videos (Shorts + live streams excluded).")
    return videos


# ---------------------------------------------------------------------------
# Step 2 — Download audio only
# ---------------------------------------------------------------------------

def download_audio(video: dict, scratch_dir: Path) -> tuple:
    """
    Download best-quality audio only for a video. Returns (path, None) on success
    or (None, error_string) on failure.
    """
    url    = video["webpage_url"]
    vid_id = video["video_id"]
    out_template = str(scratch_dir / f"{vid_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "best",
        "--audio-quality", "0",
        "--ffmpeg-location", FFMPEG_DIR,
        "--output", out_template,
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        err = result.stderr.strip()
        if any(x in err for x in ["age-restricted", "age gated", "Private video", "members-only", "unavailable"]):
            return None, err
        return None, err or "yt-dlp returned non-zero exit code"

    matches = list(scratch_dir.glob(f"{vid_id}.*"))
    if not matches:
        return None, "Audio file not found after download"

    return matches[0], None


# ---------------------------------------------------------------------------
# Step 3 — Transcribe with Whisper
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: Path, model) -> str:
    """Run Whisper base model on audio_path and return the transcript text."""
    result = model.transcribe(str(audio_path), fp16=False, verbose=False)
    return result["text"].strip()


# ---------------------------------------------------------------------------
# Step 4 — Save transcript file
# ---------------------------------------------------------------------------

def save_transcript(video: dict, transcript: str, output_dir: Path) -> Path:
    """Save transcript to voice/transcripts/<YYYYMMDD>-<id>.txt"""
    date_slug = video["upload_date"].replace("-", "") if video["upload_date"] else "unknown"
    vid_id    = video["video_id"]
    filename  = f"{date_slug}-{vid_id}.txt"

    # Sanitise description — keep first 500 chars
    desc = video.get("description", "").strip()
    if len(desc) > 500:
        desc = desc[:500] + "..."

    content = (
        f"TITLE: {video['title']}\n"
        f"DESCRIPTION: {desc}\n"
        f"DATE: {video['upload_date']}\n"
        f"VIEW COUNT: {video.get('view_count', 'N/A')}\n"
        f"LIKE COUNT: {video.get('like_count', 'N/A')}\n"
        f"COMMENT COUNT: {video.get('comment_count', 'N/A')}\n"
        f"VIDEO ID: {vid_id}\n"
        f"URL: {video['webpage_url']}\n"
        f"TRANSCRIPT:\n{transcript}\n"
    )

    out_path = output_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_channel.py <channel_url>")
        sys.exit(1)

    channel_url = sys.argv[1]

    videos = fetch_channel_videos(channel_url)
    if not videos:
        print("[error] No videos found. Check the channel URL.")
        sys.exit(1)

    # Filter out already-transcribed videos
    new_videos = []
    skipped_count = 0
    for v in videos:
        if _already_transcribed(v["video_id"]):
            print(f"  [skip] already done: *-{v['video_id']}.txt  ({v['title'][:55]})")
            skipped_count += 1
        else:
            new_videos.append(v)

    if skipped_count:
        print(f"\n  {skipped_count} video(s) already transcribed — skipping.")

    if not new_videos:
        print("\n  Nothing new to transcribe. All videos are already done.")
        print(f"  Transcripts location: {TRANSCRIPTS_DIR}")
        return

    print(f"\n[2/3] Loading Whisper base model...")
    model = whisper.load_model("base")
    print("  Model loaded.")

    total      = len(new_videos)
    transcribed = 0
    failed     = []
    total_words = 0

    print(f"\n[3/3] Transcribing {total} new video(s)...\n")

    for i, video in enumerate(new_videos, start=1):
        title  = video["title"]
        vid_id = video["video_id"]
        print(f"  [{i}/{total}] {title[:70]}")

        # Download audio
        audio_path, err = download_audio(video, SCRATCH_DIR)
        if audio_path is None:
            reason = err or "unknown error"
            print(f"         SKIPPED — {reason[:80]}")
            failed.append({"title": title, "video_id": vid_id, "reason": reason})
            continue

        # Transcribe
        try:
            transcript = transcribe_audio(audio_path, model)
        except Exception as e:
            print(f"         TRANSCRIPTION FAILED — {e}")
            failed.append({"title": title, "video_id": vid_id, "reason": str(e)})
            audio_path.unlink(missing_ok=True)
            continue

        # Save
        out_path   = save_transcript(video, transcript, TRANSCRIPTS_DIR)
        word_count = len(transcript.split())
        total_words += word_count
        transcribed += 1

        # Delete scratch audio
        audio_path.unlink(missing_ok=True)

        print(f"         OK — {word_count} words → {out_path.name}")
        print(f"  Transcribed {transcribed}/{total}")

    # Clean up scratch dir if empty
    try:
        SCRATCH_DIR.rmdir()
    except OSError:
        pass

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Already done:  {skipped_count}")
    print(f"  New this run:  {transcribed}/{total}")
    print(f"  Total words:   {total_words:,}")
    if failed:
        print(f"  Failed/Skipped ({len(failed)}):")
        for f in failed:
            print(f"    - [{f['video_id']}] {f['title'][:50]} — {f['reason'][:60]}")
    print(f"\n  Transcripts saved to: {TRANSCRIPTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
