"""
gather_clips.py — Highlight Clip Downloader
============================================
Full workflow:
  1. Accept a topic + optional YouTube URLs (or read from scripted outline)
  2. Load clip sources from config/clip_sources.json
  3. Search approved YouTube channels via YouTube Data API (needs YOUTUBE_DATA_API_KEY)
     OR accept --urls directly (no API key needed)
  4. For each video: show title/URL, prompt for start/end timestamps
  5. Download just that segment using yt-dlp (--download-sections)
  6. Save each clip to clips/raw/ with a sidecar metadata JSON file

Clip rules (always enforced):
  - Strictly < 5 seconds per clip (MAX_CLIP_DURATION = 4.9s)
  - Game footage only — interviews, press conferences, practice videos are filtered out
  - Horizontal format only (width > height); vertical/Shorts are skipped
  - Minimum 10-second gap between consecutive clips from the same source video
  - visual_break_after: true flag in every metadata JSON (assemble_video.py inserts a
    stat board / screenshot overlay between clips — required for copyright safety)

Run:
    # Fully automated — reads outline sections, searches YouTube, picks timestamps:
    python gather_clips.py --from-outline --auto

    # Auto with explicit topic override:
    python gather_clips.py --topic "McKenna comeback" --auto

    # Interactive — you paste URLs and enter timestamps (6s cap enforced):
    python gather_clips.py --topic "McKenna comeback" --urls "https://youtube.com/watch?v=..."

    # Interactive from outline clip cues:
    python gather_clips.py --from-outline

Output:
    clips/raw/mckenna-comeback-001.mp4
    clips/raw/mckenna-comeback-001.json   (metadata sidecar)
"""

import os
import re
import json
import math
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

import html
import yt_dlp
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config and paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

YOUTUBE_API_KEY     = os.getenv("YOUTUBE_DATA_API_KEY")
CLIP_SOURCES_CONFIG = _PROJECT_ROOT / "config" / "clip_sources.json"
SCRIPTED_DIR        = _PROJECT_ROOT / "pipeline" / "scripted"
RECORDED_DIR        = _PROJECT_ROOT / "pipeline" / "recorded"
RAW_CLIPS_DIR       = _PROJECT_ROOT / "clips" / "raw"
FFMPEG_DIR          = "/opt/homebrew/bin"
COOKIES_FILE        = _PROJECT_ROOT / "config" / "youtube-cookies.txt"

# Clip quality rules
MAX_CLIP_DURATION    = 4.9   # seconds — hard cap, strictly < 5s (copyright rule)
TARGET_CLIP_DURATION = 4.0   # seconds — target window in auto-mode
INTRO_SKIP_PCT       = 0.20  # skip first 20% of any video (title cards)
OUTRO_SKIP_PCT       = 0.10  # stop 10% before end (end cards / screens)
MIN_VIDEO_DURATION   = 20.0  # skip videos shorter than this (Shorts / teasers)
MIN_CLIP_GAP_SECONDS = 10.0  # minimum gap (seconds) between consecutive clips from the same source video

# Keywords that indicate non-game content — these video titles are rejected
_NON_GAME_TITLE_KEYWORDS = {
    "interview", "press conference", "mic'd up", "mic up", "micd up",
    "uncut", "practice", "training camp", "media day", "availability",
    "q&a", "behind the scenes", "off ice", "locker room interview",
    "morning skate", "pre-game",
}


def _is_game_footage(title: str) -> bool:
    """Return True if the video title suggests in-game footage, not an interview or practice."""
    title_lower = title.lower()
    return not any(kw in title_lower for kw in _NON_GAME_TITLE_KEYWORDS)


def _build_highlight_query(topic: str) -> str:
    """
    Append NHL highlight qualifiers to the search query if none are already present.
    Ensures we get in-game footage, not interviews or press conferences.
    """
    topic_lower = topic.lower()
    has_qualifier = any(
        kw in topic_lower for kw in ("highlight", "goal", " game", "nhl")
    )
    if has_qualifier:
        return topic
    return f"{topic} NHL highlights"

AUDIO_EXTENSIONS = {".mp4", ".mov", ".m4a", ".wav", ".aac"}

# Add Homebrew to PATH so yt-dlp can find ffmpeg
os.environ["PATH"] = FFMPEG_DIR + ":" + os.environ.get("PATH", "")


def _yt_base_cli_flags() -> list[str]:
    """
    Return yt-dlp CLI flags to bypass YouTube bot detection and n-challenge.
    - Firefox cookies: bot check bypass
    - Node.js + EJS from GitHub: n-challenge solver (cached after first run)
    - ffmpeg-location: for merging video+audio streams
    """
    cookie_flags = (
        ["--cookies", str(COOKIES_FILE)]
        if COOKIES_FILE.exists()
        else ["--cookies-from-browser", "firefox"]
    )
    return [
        *cookie_flags,
        "--js-runtimes", "node:/usr/local/bin/node",
        "--remote-components", "ejs:github",
        "--ffmpeg-location", FFMPEG_DIR,
    ]


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def load_clip_sources() -> dict:
    with open(CLIP_SOURCES_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Voiceover duration
# ---------------------------------------------------------------------------

def get_voiceover_duration() -> float:
    """Return duration in seconds of the most recent voiceover file in pipeline/recorded/."""
    files = sorted(
        [f for f in RECORDED_DIR.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS],
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    if not files:
        return 90.0  # fallback
    result = subprocess.run(
        [
            "/opt/homebrew/bin/ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(files[0]),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 90.0


# ---------------------------------------------------------------------------
# Outline parsing — section-based (auto mode)
# ---------------------------------------------------------------------------

def _extract_subject_from_title(title: str) -> str:
    """
    Extract the main 2-3 word subject from an outline title.
    e.g. "Outline: Gavin McKenna Just Had..." → "Gavin McKenna"
    """
    # Strip common doc-type prefixes
    title = re.sub(r"^(outline|script|episode|draft)[:\s]+", "", title, flags=re.IGNORECASE).strip()
    stop_at = {
        "just", "had", "has", "is", "are", "was", "were", "the", "a", "an",
        "and", "or", "—", "but", "still", "one", "of", "in", "at", "for",
        "greatest", "best", "worst", "why", "how", "what", "people",
    }
    words = re.sub(r"[^\w\s]", " ", title).split()
    subject_words = []
    for w in words:
        if w.lower() in stop_at or len(subject_words) >= 3:
            break
        subject_words.append(w)
    return " ".join(subject_words)


def parse_outline_sections(outline_path: Path = None, topic: str = "") -> list[dict]:
    """
    Parse outline sections and return per-section search queries.
    Each section → {"section": heading, "query": search_string, "clips_needed": 0}.

    Priority for query building:
    1. *(placeholder — replace with X)* comment → use X as query
    2. [CLIP: description] marker → use description
    3. Heading text keyword extraction
    """
    if outline_path is None:
        files = sorted(SCRIPTED_DIR.glob("*.md"), reverse=True)
        if not files:
            return []
        outline_path = files[0]

    text = outline_path.read_text(encoding="utf-8")

    # Extract the document title for subject prefix
    title_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else topic
    subject = _extract_subject_from_title(doc_title)

    # Split on ## headings
    raw_sections = re.split(r"\n(?=## )", text)

    stop_words = {
        "the", "a", "an", "of", "in", "for", "and", "or", "at", "to",
        "—", "-", "still", "being", "just", "what", "how", "why", "is",
        "was", "were", "had", "have", "has", "it", "its", "case", "game",
        "start", "point", "points", "actually", "happened", "misread",
        "breaking", "down", "still",
    }

    sections = []
    for block in raw_sections:
        heading_match = re.match(r"## (.+)", block)
        if not heading_match:
            continue
        heading = heading_match.group(1).strip()

        # Skip outro — no new footage needed
        if re.match(r"outro", heading, re.IGNORECASE):
            continue

        # Priority 1: placeholder replacement hint
        placeholder_match = re.search(
            r"\*\(placeholder[^)]*replace with ([^)]+)\)",
            block, re.IGNORECASE,
        )
        if placeholder_match:
            hint = placeholder_match.group(1).strip()
            # Clean "or"-separated alternatives — take first
            hint = re.split(r"\bor\b", hint, maxsplit=1)[0].strip()
            # Remove "clip" word, trailing punctuation
            hint = re.sub(r"\bclip\b", "", hint, flags=re.IGNORECASE).strip().strip("/").strip()
            # Prefix subject if none of its words appear in hint
            if subject:
                subj_words = set(subject.lower().split())
                hint_words = set(hint.lower().split())
                if not (subj_words & hint_words):
                    query = f"{subject} {hint}"
                else:
                    query = hint
            else:
                query = hint
            sections.append({"section": heading, "query": query.strip()[:80], "clips_needed": 0})
            continue

        # Priority 2: [CLIP: description] marker
        clip_marker = re.search(r"\[CLIP:\s*(.+?)\]", block, re.IGNORECASE)
        if clip_marker:
            cue = clip_marker.group(1).strip()
            # Strip " — channel" suffix
            cue = re.split(r"\s*[—–-]\s*(?:NHL|Sportsnet|TSN|ESPN|BarDown|placeholder.*)", cue)[0].strip()
            cue = cue.strip("*").strip()
            if not (re.match(r"^\d{2}-", cue) or "placeholder" in cue.lower()):
                if subject:
                    subj_words = set(subject.lower().split())
                    cue_words  = set(cue.lower().split())
                    if not (subj_words & cue_words):
                        query = f"{subject} {cue}"
                    else:
                        query = cue
                else:
                    query = cue
                sections.append({"section": heading, "query": query.strip()[:80], "clips_needed": 0})
                continue

        # Priority 3: extract keywords from heading + first bullet points
        clean_heading = re.sub(r"^Section\s+\d+[:\s]+", "", heading, flags=re.IGNORECASE).strip()
        # Remove parentheticals — but check if they contain good keywords first
        paren_match = re.search(r"\(([^)]+)\)", clean_heading)
        paren_text = paren_match.group(1) if paren_match else ""
        heading_source = paren_text if paren_text else clean_heading

        # Also extract keywords from first 2 bullet points in the block
        bullet_texts = re.findall(r"^[-*]\s+(.+)", block, re.MULTILINE)[:2]
        bullet_pool = " ".join(bullet_texts)

        combined = f"{heading_source} {bullet_pool}"
        keywords = [
            w for w in re.sub(r"[^\w\s]", " ", combined).split()
            if w.lower() not in stop_words and len(w) > 2
        ]
        # Deduplicate while preserving order
        seen_kw = set()
        unique_kw = []
        for w in keywords:
            if w.lower() not in seen_kw:
                seen_kw.add(w.lower())
                unique_kw.append(w)
        heading_phrase = " ".join(unique_kw[:5])

        # Build query; avoid duplicating subject words already in heading_phrase
        if subject:
            subj_words = set(subject.lower().split())
            phrase_words = set(heading_phrase.lower().split())
            if subj_words & phrase_words:
                query = heading_phrase  # subject already present
            else:
                query = f"{subject} {heading_phrase}".strip()
        else:
            query = heading_phrase

        sections.append({"section": heading, "query": query.strip()[:80], "clips_needed": 0})

    return sections


# ---------------------------------------------------------------------------
# Outline parsing — [CLIP: ...] markers (interactive --from-outline mode)
# ---------------------------------------------------------------------------

def parse_clip_cues_from_outline(outline_path: Path = None) -> list[str]:
    """
    Read the latest scripted outline and extract [CLIP: description] markers.
    Returns a list of search query strings, one per clip cue.
    """
    if outline_path is None:
        files = sorted(SCRIPTED_DIR.glob("*.md"), reverse=True)
        if not files:
            return []
        outline_path = files[0]

    print(f"[gather_clips] Reading clip cues from: {outline_path.name}")
    text = outline_path.read_text(encoding="utf-8")

    raw_cues = re.findall(r"\[CLIP:\s*(.+?)\]", text, re.IGNORECASE)

    queries = []
    for cue in raw_cues:
        query = re.split(r"\s*[—–-]\s*(?:NHL|Sportsnet|TSN|ESPN|BarDown|placeholder.*)", cue)[0]
        query = query.strip().strip("*")
        if re.match(r"^\d{2}-", query) or "placeholder" in query.lower():
            continue
        if query:
            queries.append(query)

    return queries


# ---------------------------------------------------------------------------
# YouTube Data API search (requires YOUTUBE_DATA_API_KEY)
# ---------------------------------------------------------------------------

def search_youtube_for_clips(
    topic: str,
    channel_ids: list[str],
    max_results: int = 5,
) -> list[dict]:
    """
    Search approved YouTube channels for in-game highlight footage matching the topic.
    Requires YOUTUBE_DATA_API_KEY in config/.env.

    Automatically appends NHL highlight qualifiers to the query and filters out
    non-game videos (interviews, press conferences, practice footage, etc.).

    Returns list of dicts: video_id, title, channel, published_at, url.
    """
    if not YOUTUBE_API_KEY:
        print("[gather_clips] No YOUTUBE_DATA_API_KEY — use --urls to provide URLs directly.")
        return []

    from googleapiclient.discovery import build

    # Always search for game footage specifically
    search_query = _build_highlight_query(topic)

    results = []
    seen_ids = set()
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        for channel_id in channel_ids:
            try:
                response = youtube.search().list(
                    q=search_query,
                    channelId=channel_id,
                    type="video",
                    order="relevance",
                    maxResults=max_results,
                    part="snippet",
                ).execute()

                for item in response.get("items", []):
                    vid_id = item["id"]["videoId"]
                    if vid_id in seen_ids:
                        continue
                    seen_ids.add(vid_id)
                    snippet = item["snippet"]
                    title = html.unescape(snippet.get("title", ""))

                    # Reject non-game footage by title
                    if not _is_game_footage(title):
                        print(f"[gather_clips] Filtered (non-game): {title[:60]}")
                        continue

                    results.append({
                        "video_id":     vid_id,
                        "title":        title,
                        "channel":      html.unescape(snippet.get("channelTitle", "")),
                        "published_at": snippet.get("publishedAt", ""),
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                    })
            except Exception as e:
                print(f"[gather_clips] Search error for channel {channel_id}: {e}")
    except Exception as e:
        print(f"[gather_clips] YouTube API error: {e}")

    return results


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------

def get_video_info(url: str) -> dict:
    """Fetch title, duration, channel, width, height for a YouTube URL via yt-dlp CLI."""
    cmd = [
        "yt-dlp",
        *_yt_base_cli_flags(),
        "--skip-download",
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s\t%(width)s\t%(height)s",
        "--no-warnings", "--quiet",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("\t", 5)
            width  = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
            height = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
            return {
                "video_id": parts[0] if len(parts) > 0 else "",
                "title":    parts[1] if len(parts) > 1 else url,
                "channel":  parts[2] if len(parts) > 2 else "Unknown",
                "duration": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
                "width":    width,
                "height":   height,
                "url":      url,
            }
    except Exception as e:
        print(f"[gather_clips] Could not fetch info for {url}: {e}")
    return {
        "video_id": "", "title": url, "channel": "Unknown",
        "duration": 0, "width": 0, "height": 0, "url": url,
    }


def download_clip_segment(
    video_url: str,
    start_seconds: float,
    end_seconds: float,
    output_path: Path,
) -> bool:
    """
    Download a specific time-range segment from a YouTube video using yt-dlp.
    Enforces MAX_CLIP_DURATION — end is capped if the range exceeds it.
    """
    # Hard cap — never download more than MAX_CLIP_DURATION seconds
    if end_seconds - start_seconds > MAX_CLIP_DURATION:
        end_seconds = start_seconds + MAX_CLIP_DURATION

    output_path.parent.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_path.with_suffix("")) + ".%(ext)s"
    section = f"*{start_seconds}-{end_seconds}"

    cmd = [
        "yt-dlp",
        *_yt_base_cli_flags(),
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "--no-warnings", "--quiet",
        "-o", outtmpl,
        video_url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[gather_clips] yt-dlp error: {result.stderr[:200]}")
            return False

        parent = output_path.parent
        stem = output_path.stem
        for ext in (".mp4", ".mkv", ".webm"):
            candidate = parent / (stem + ext)
            if candidate.exists():
                if candidate != output_path:
                    candidate.rename(output_path)
                return True

        return output_path.exists()

    except Exception as e:
        print(f"[gather_clips] Download failed: {e}")
        return False


def save_clip_metadata(
    output_path: Path,
    video: dict,
    start_seconds: float,
    end_seconds: float,
    topic: str,
    section: str = "",
):
    metadata = {
        "source_url":       video.get("url", ""),
        "channel_name":     video.get("channel", ""),
        "video_title":      video.get("title", ""),
        "timestamp_start":  start_seconds,
        "timestamp_end":    end_seconds,
        "duration":         round(end_seconds - start_seconds, 2),
        "topic":            topic,
        "section":          section,
        "downloaded_at":    datetime.utcnow().isoformat(),
        # assemble_video.py MUST insert a visual break (stat board / player screenshot)
        # after this clip before the next clip begins — required to avoid consecutive clips
        # that trigger YouTube copyright detection.
        "visual_break_after": True,
    }
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Auto-mode: smart window picking
# ---------------------------------------------------------------------------

def pick_clip_windows(
    video_duration: float,
    clip_duration: float = TARGET_CLIP_DURATION,
    n_clips: int = 1,
) -> list[tuple]:
    """
    Return N evenly-spaced (start, end) windows from the video's "action zone".
    Skips the first INTRO_SKIP_PCT (title cards) and last OUTRO_SKIP_PCT (end cards).
    Each window is at most MAX_CLIP_DURATION seconds.

    Enforces MIN_CLIP_GAP_SECONDS between consecutive clips from the same source video.
    Any clip that falls within the minimum gap of the previous one is dropped.
    """
    clip_duration = min(clip_duration, MAX_CLIP_DURATION)
    action_start  = video_duration * INTRO_SKIP_PCT
    action_end    = video_duration * (1.0 - OUTRO_SKIP_PCT)
    action_range  = action_end - action_start

    if action_range < clip_duration:
        # Very short video — just take from action_start
        s = max(0.0, action_start)
        return [(s, min(s + clip_duration, video_duration))]

    # Evenly distribute n_clips across the action zone
    step = action_range / max(n_clips, 1)
    candidates = []
    for i in range(n_clips):
        s = action_start + i * step
        e = min(s + clip_duration, action_end)
        candidates.append((round(s, 2), round(e, 2)))

    # Enforce minimum gap between consecutive clips
    # (prevents back-to-back footage from the same source video triggering copyright)
    validated = [candidates[0]]
    for start, end in candidates[1:]:
        prev_end = validated[-1][1]
        if start - prev_end >= MIN_CLIP_GAP_SECONDS:
            validated.append((start, end))
        # else: too close to previous clip — skip this window

    return validated


# ---------------------------------------------------------------------------
# Timestamp input helper (interactive mode)
# ---------------------------------------------------------------------------

def parse_timestamp(ts: str) -> float:
    """Convert MM:SS or HH:MM:SS or raw seconds string to float seconds."""
    ts = ts.strip()
    if not ts:
        return -1.0
    parts = ts.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    return -1.0


def slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:50].strip("-")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def gather_clips_for_topic(
    topic: str,
    max_clips: int = 6,
    urls: list[str] = None,
    from_outline: bool = False,
    auto: bool = False,
):
    """
    Full pipeline: find videos → select timestamps → download segments → save metadata.

    auto=True  — fully non-interactive; reads outline sections, searches YouTube,
                 picks timestamps from the action zone. Fills the voiceover duration.
    auto=False — interactive; prompts for timestamps. Enforces 6s max.
    """
    RAW_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)

    # =========================================================================
    # AUTO MODE
    # =========================================================================
    if auto:
        if not YOUTUBE_API_KEY:
            print("[gather_clips] --auto requires YOUTUBE_DATA_API_KEY in config/.env.")
            return

        vo_dur = get_voiceover_duration()
        total_clips_needed = math.ceil(vo_dur / TARGET_CLIP_DURATION) + 2
        print(f"[gather_clips] Voiceover: {vo_dur:.1f}s")
        print(f"[gather_clips] Clips needed: {total_clips_needed} (≤{MAX_CLIP_DURATION:.0f}s each)")

        sources = load_clip_sources()
        channel_ids = [
            ch["channel_id"]
            for ch in sources.get("youtube_highlight_channels", [])
            if ch.get("channel_id")
        ]

        # Parse outline sections for context-aware queries
        sections = parse_outline_sections(topic=topic)
        if not sections:
            sections = [{"section": "Main", "query": topic, "clips_needed": total_clips_needed}]
        else:
            per_section = math.ceil(total_clips_needed / len(sections))
            for s in sections:
                s["clips_needed"] = per_section
            print(f"[gather_clips] {len(sections)} outline sections → ~{per_section} clips each\n")

        downloaded = 0
        failed_sections = []

        for sec in sections:
            query = sec["query"]
            n_needed = sec["clips_needed"]
            print(f"--- Section: {sec['section']}")
            print(f"    Query:   {query}")

            candidates = search_youtube_for_clips(query, channel_ids, max_results=5)
            if not candidates:
                print(f"    ✗ No search results — skipping.\n")
                failed_sections.append(sec["section"])
                continue

            # Find first usable (horizontal, long enough) video
            video = None
            for c in candidates:
                info = get_video_info(c["url"])
                dur = info.get("duration", 0)
                w   = info.get("width", 0)
                h   = info.get("height", 0)

                # Skip Shorts / very short videos
                if dur < MIN_VIDEO_DURATION:
                    print(f"    ↷ Too short ({dur}s): {info['title'][:55]}")
                    continue

                # Skip vertical (portrait) videos — width/height both 0 means unknown, allow
                if w > 0 and h > 0 and h > w:
                    print(f"    ↷ Vertical ({w}×{h}): {info['title'][:55]}")
                    continue

                # Merge API fields into yt-dlp info
                for k, v in c.items():
                    if k not in info:
                        info[k] = v
                video = info
                break  # found a usable video

            if video is None:
                print(f"    ✗ No usable horizontal video found.\n")
                failed_sections.append(sec["section"])
                continue

            dur     = video["duration"]
            dur_str = f"{int(dur)//60}:{int(dur)%60:02d}"
            print(f"    ✓ {video['title'][:65]}")
            print(f"      Channel: {video['channel']}  |  Duration: {dur_str}")

            windows = pick_clip_windows(dur, TARGET_CLIP_DURATION, n_needed)

            for start, end in windows:
                clip_num = downloaded + 1
                out_path = RAW_CLIPS_DIR / f"{slug}-{clip_num:03d}.mp4"
                s_str = f"{int(start)//60}:{int(start)%60:05.2f}"
                e_str = f"{int(end)//60}:{int(end)%60:05.2f}"
                print(f"      ↓ Clip {clip_num:02d}: {s_str}–{e_str}  ({end-start:.1f}s)")

                ok = download_clip_segment(video["url"], start, end, out_path)
                if ok:
                    save_clip_metadata(out_path, video, start, end, topic, section=sec["section"])
                    downloaded += 1
                    size_kb = out_path.stat().st_size // 1024
                    print(f"               ✓ {out_path.name}  ({size_kb} KB)")
                else:
                    print(f"               ✗ Download failed.")
                    failed_sections.append(f"{sec['section']} clip {clip_num}")
            print()

        total_secs = downloaded * TARGET_CLIP_DURATION
        print("=" * 55)
        print(f"DONE  |  Clips: {downloaded}  |  Sections failed: {len(failed_sections)}")
        print(f"Total clip duration: ~{total_secs:.0f}s  (voiceover: {vo_dur:.1f}s)")
        if downloaded:
            print(f"Clips saved to: {RAW_CLIPS_DIR}")
            print("Review them, then move keepers to clips/approved/")
        for f in failed_sections:
            print(f"  ✗ {f}")
        print("=" * 55)
        return

    # =========================================================================
    # INTERACTIVE MODE
    # =========================================================================
    videos = []

    if urls:
        print(f"\n[gather_clips] Fetching info for {len(urls)} provided URL(s)...")
        for url in urls:
            info = get_video_info(url)
            videos.append(info)
            dur = info["duration"]
            print(f"  ✓ {info['title'][:70]} ({dur//60}:{dur%60:02d}) — {info['channel']}")

    elif from_outline:
        queries = parse_clip_cues_from_outline()
        if not queries:
            print("[gather_clips] No [CLIP: ...] markers found in the latest outline.")
            return
        print(f"\n[gather_clips] Found {len(queries)} clip cue(s) from outline:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")

        if not YOUTUBE_API_KEY:
            print("\n[gather_clips] No YOUTUBE_DATA_API_KEY — paste URLs manually.")
            for i, q in enumerate(queries, 1):
                url = input(f"  URL for clip {i} '{q}' (Enter to skip): ").strip()
                if url:
                    info = get_video_info(url)
                    info["_cue"] = q
                    videos.append(info)
        else:
            sources = load_clip_sources()
            channel_ids = [
                ch["channel_id"]
                for ch in sources.get("youtube_highlight_channels", [])
                if ch.get("channel_id")
            ]
            for q in queries[:max_clips]:
                found = search_youtube_for_clips(q, channel_ids, max_results=3)
                videos.extend(found)

    else:
        if not YOUTUBE_API_KEY:
            print("[gather_clips] No YOUTUBE_DATA_API_KEY. Use --urls to provide YouTube URLs directly.")
            print("  Example: python gather_clips.py --topic '...' --urls 'https://youtube.com/watch?v=...'")
            return
        sources = load_clip_sources()
        channel_ids = [
            ch["channel_id"]
            for ch in sources.get("youtube_highlight_channels", [])
            if ch.get("channel_id")
        ]
        videos = search_youtube_for_clips(topic, channel_ids, max_results=max_clips)

    if not videos:
        print("[gather_clips] No videos to process.")
        return

    print(f"\n[gather_clips] Processing {len(videos)} video(s)...")
    print(f"  Clips are capped at {MAX_CLIP_DURATION}s max (strictly <5s) — enter timestamps accordingly.")
    print("  Press Enter on start to skip a video.\n")

    downloaded = 0
    failed = []

    for i, video in enumerate(videos, 1):
        dur = video.get("duration", 0)
        dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else "?"
        print(f"[{i}/{len(videos)}] {video['title'][:70]}")
        print(f"         Channel: {video['channel']}  |  Duration: {dur_str}")
        print(f"         URL: {video['url']}")

        start_str = input("         Start (MM:SS, or Enter to skip): ").strip()
        if not start_str:
            print("         Skipped.\n")
            continue

        end_str = input(f"         End   (MM:SS, ≤{MAX_CLIP_DURATION:.0f}s from start): ").strip()

        start = parse_timestamp(start_str)
        end   = parse_timestamp(end_str)

        if start < 0 or end < 0 or end <= start:
            print("         Invalid timestamps — skipped.\n")
            continue

        # Enforce 6s hard cap
        if end - start > MAX_CLIP_DURATION:
            end = start + MAX_CLIP_DURATION
            cap_end_str = f"{int(end)//60}:{int(end)%60:02d}"
            print(f"         ⚠  Capped to {MAX_CLIP_DURATION:.0f}s → end adjusted to {cap_end_str}")

        clip_num = downloaded + 1
        out_path = RAW_CLIPS_DIR / f"{slug}-{clip_num:03d}.mp4"

        print(f"         Downloading {start_str}–{end_str} ({end-start:.0f}s)...")
        ok = download_clip_segment(video["url"], start, end, out_path)

        if ok:
            save_clip_metadata(out_path, video, start, end, topic)
            downloaded += 1
            size_kb = out_path.stat().st_size // 1024
            print(f"         ✓ Saved → {out_path.name} ({size_kb} KB)\n")
        else:
            print(f"         ✗ Download failed.\n")
            failed.append(video["title"])

    print("=" * 55)
    print(f"DONE  |  Downloaded: {downloaded}  |  Failed: {len(failed)}")
    if downloaded:
        print(f"Clips saved to: {RAW_CLIPS_DIR}")
        print("Review them, then move keepers to clips/approved/")
    if failed:
        for t in failed:
            print(f"  ✗ {t[:60]}")
    print("=" * 55)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search and download highlight clips for a given topic."
    )
    parser.add_argument(
        "--topic", type=str, default="",
        help="Topic to search for (e.g. 'Gavin McKenna Ohio State highlights')"
    )
    parser.add_argument(
        "--urls", type=str, nargs="+", default=[],
        help="One or more YouTube URLs (skips search, no API key needed)"
    )
    parser.add_argument(
        "--from-outline", action="store_true",
        help="Read [CLIP: ...] cues from the latest scripted outline"
    )
    parser.add_argument(
        "--auto", action="store_true",
        help=(
            "Fully automated: reads outline sections, searches YouTube, "
            "picks timestamps automatically (requires YOUTUBE_DATA_API_KEY)"
        ),
    )
    parser.add_argument(
        "--max-clips", type=int, default=6,
        help="Max clips when using API search without --auto (default: 6)"
    )
    args = parser.parse_args()

    if not args.topic and not args.from_outline:
        parser.error("Provide --topic or --from-outline")

    topic = args.topic
    if args.from_outline and not topic:
        files = sorted(SCRIPTED_DIR.glob("*.md"), reverse=True)
        if files:
            topic = files[0].stem.replace("-", " ").strip()
        else:
            topic = "hockey highlights"

    gather_clips_for_topic(
        topic=topic,
        max_clips=args.max_clips,
        urls=args.urls,
        from_outline=args.from_outline,
        auto=args.auto,
    )


if __name__ == "__main__":
    main()
