"""
gather_clips.py — Highlight Clip Downloader
============================================
Full workflow:
  1. Accept a topic or read clip cues from the project outline
  2. Load clip sources from config/clip_sources.json
  3. Search YouTube, Reddit, and trusted web sources for usable hockey footage
  4. Download short edit-ready segments with yt-dlp
  5. Save clips to clips/<project>/raw/

Clip rules (always enforced):
  - Strictly < 5 seconds per clip (MAX_CLIP_DURATION = 4.9s)
  - Real game footage first; relevant interviews/graphics are allowed in auto mode
  - Horizontal format only (width > height); vertical short-form clips are skipped
  - At most 2 clips per source video, spaced at least 60 seconds apart

Run:
    # Fully automated — reads outline sections, searches YouTube, picks timestamps:
    python3 gather_clips.py --from-outline --auto

    # Auto with explicit topic override:
    python3 gather_clips.py --topic "McKenna comeback" --auto

Output:
    clips/2026-05-29-topic-slug/raw/01-section-name-source-title.mp4
    clips/2026-05-29-topic-slug/raw/01-section-name-source-title.json
"""

import os
import re
import json
import math
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import html
import urllib.parse
import urllib.request
import yt_dlp
from dotenv import load_dotenv
from utils.projects import latest_script, resolve_project, write_default_requirements

# ---------------------------------------------------------------------------
# Config and paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

YOUTUBE_API_KEY     = os.getenv("YOUTUBE_DATA_API_KEY")
CLIP_SOURCES_CONFIG = _PROJECT_ROOT / "config" / "clip_sources.json"
SCRIPTED_DIR        = _PROJECT_ROOT / "03_Reference" / "past-scripts"
RECORDED_DIR        = _PROJECT_ROOT / "03_Reference"
RAW_CLIPS_DIR       = _PROJECT_ROOT / "clips" / "raw"
FFMPEG_DIR          = "/opt/homebrew/bin"
COOKIES_FILE        = _PROJECT_ROOT / "config" / "youtube-cookies.txt"

# Clip quality rules
MIN_CLIP_DURATION    = 3.0   # seconds — hard floor (clips shorter than this are skipped)
MAX_CLIP_DURATION    = 4.9   # seconds — hard cap, strictly < 5s (copyright rule)
TARGET_CLIP_DURATION = 4.0   # seconds — target window in auto-mode
INTRO_SKIP_PCT       = 0.20  # skip first 20% of any video (title cards)
OUTRO_SKIP_PCT       = 0.10  # stop 10% before end (end cards / screens)
MIN_VIDEO_DURATION   = 20.0  # skip videos shorter than this
MIN_CLIP_GAP_SECONDS = 60.0  # minimum gap (seconds) between clips from the same source video
CLIPS_PER_VIDEO_MAX  = 2     # max clips taken from any single source video (copyright safety)
_REDDIT_BLOCKED_SUBREDDITS: set[str] = set()

# Candidate classification. Interviews/graphics are allowed when relevant;
# gameplay, podcasts, and unrelated talking heads are rejected for client demos.
_GAMEPLAY_KEYWORDS = {
    "xbox", "ea sports", "nhl 24", "nhl 25", "nhl 26", "gameplay",
    "franchise mode", "be a pro", "simulation", "simulated", "hockey ultimate team",
    "hut pack", "ps5", "playstation", "xbox series",
}
_TALKING_HEAD_KEYWORDS = {
    "podcast", "live stream", "livestream", "stream highlights", "watchalong",
    "reaction show", "radio show", "daily podcast", "locked on", "mailbag",
    "fans react", "fan first network", "real kyper", "bourne clips",
    "what's matt rempe's future", "future with the new york rangers",
    "what the hell did we actually just witness", "nhl network",
}
_TITLE_CARD_KEYWORDS = {
    "full clip coming", "full clip", "subscribe", "subscribed", "like and subscribe",
    "smash that like", "turn on notifications", "lineups", "intro", "outro",
    "how do i get out", "all star game",
}
_KNOWN_BAD_CHANNELS = {
    "center ice central", "creepthejeep", "jonathan hawkey", "hawkey productions",
    "next man up", "eck", "nuckhead", "habscentral", "hockey trend",
}
_INTERVIEW_KEYWORDS = {
    "interview", "press conference", "media availability", "availability",
    "scrum", "postgame", "post-game", "locker room", "speaks", "on his",
}
_GRAPHIC_KEYWORDS = {
    "scouting report", "draft ranking", "rankings", "stats", "breakdown",
    "profile", "prospect profile", "analysis",
}
_GAME_KEYWORDS = {
    "highlight", "highlights", "goal", "goals", "fight", "hit", "shift",
    "all shifts", "vs", "versus", "recap", "game", "shootout",
}


def classify_candidate(video: dict, topic_keywords: list[str] = None) -> str:
    """
    Classify a candidate as game/interview/graphic/talking_head/gameplay/reject.
    Topic relevance is checked before calling this in auto mode; this function
    handles visual suitability.
    """
    title = video.get("title", "")
    desc = video.get("description", "")
    channel = video.get("channel", "")
    text = f"{title} {desc} {channel}".lower()
    topic_keywords = topic_keywords or []

    if any(kw in text for kw in _GAMEPLAY_KEYWORDS):
        return "gameplay"
    if channel.lower().strip() in _KNOWN_BAD_CHANNELS:
        return "reject"
    if any(kw in text for kw in _TITLE_CARD_KEYWORDS):
        return "reject"
    if any(kw in text for kw in _TALKING_HEAD_KEYWORDS):
        return "talking_head"
    if any(kw in text for kw in _INTERVIEW_KEYWORDS):
        return "interview" if _matches_topic_keywords(video, topic_keywords) else "reject"
    if any(kw in text for kw in _GRAPHIC_KEYWORDS):
        return "graphic" if _matches_topic_keywords(video, topic_keywords) else "reject"
    if any(kw in text for kw in _GAME_KEYWORDS):
        return "game"
    return "game" if _matches_topic_keywords(video, topic_keywords) else "reject"


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

QUERY_TEMPLATES = [
    "{topic}",
    "{topic} highlights",
    "{topic} NHL",
    "{topic} goal",
    "{topic} best moments",
    "{player} hockey",
]

_TOPIC_STOP_WORDS = {
    "the", "a", "an", "of", "in", "is", "and", "for", "to", "with",
}
_QUERY_QUALIFIER_WORDS = {
    "highlight", "highlights", "nhl", "goal", "goals", "best", "moments", "hockey",
}


def _subject_for_query(topic: str) -> str:
    """Return the first 1-2 meaningful words for the player/subject query variant."""
    words = [
        w for w in re.sub(r"[^\w\s]", " ", topic).split()
        if (
            w.lower() not in _TOPIC_STOP_WORDS
            and w.lower() not in _QUERY_QUALIFIER_WORDS
            and len(w) >= 3
        )
    ]
    if not words:
        return topic.strip()
    return " ".join(words[:2])


def build_query_expansions(topic: str) -> list[str]:
    """Build deduped search query variants for a topic or outline section query."""
    topic = topic.strip()
    player = _subject_for_query(topic)
    topic_lower = topic.lower()
    raw_queries = [
        topic,
        topic if "highlight" in topic_lower else f"{topic} highlights",
        topic if "nhl" in topic_lower else f"{topic} NHL",
        topic if "goal" in topic_lower else f"{topic} goal",
        topic if "best moment" in topic_lower else f"{topic} best moments",
        f"{player} hockey",
    ]
    queries = []
    seen = set()
    for raw_query in raw_queries:
        query = raw_query.strip()
        query = re.sub(r"\s+", " ", query)
        key = query.lower()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def extract_topic_keywords(topic: str) -> list[str]:
    """Return relevance keywords from a topic string."""
    return [
        w.lower()
        for w in re.sub(r"[^\w\s]", " ", topic).split()
        if w.lower() not in _TOPIC_STOP_WORDS and len(w) >= 4
    ]


def _matches_topic_keywords(video: dict, keywords: list[str]) -> bool:
    """
    True when enough topic keywords appear in the title/description.
    Requires 2+ matches when 3+ keywords are available to avoid false positives
    where a player name alone triggers inclusion of completely off-topic videos.
    """
    if not keywords:
        return True
    haystack = f"{video.get('title', '')} {video.get('description', '')}".lower()
    matches = sum(1 for kw in keywords if kw in haystack)
    threshold = 2 if len(keywords) >= 3 else 1
    return matches >= threshold


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
# Target clip count
# ---------------------------------------------------------------------------

def get_target_duration(recorded_dir: Path = RECORDED_DIR) -> float:
    """Return a target duration for estimating how many raw clips to gather."""
    files = sorted(
        [f for f in recorded_dir.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS] if recorded_dir.exists() else [],
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


def parse_outline_sections(outline_path: Path = None, topic: str = "", script_dir: Path = SCRIPTED_DIR) -> list[dict]:
    """
    Parse outline sections and return per-section search queries.
    Each section → {"section": heading, "query": search_string, "clips_needed": 0}.

    Priority for query building:
    1. *(placeholder — replace with X)* comment → use X as query
    2. [CLIP: description] marker → use description
    3. Heading text keyword extraction
    """
    if outline_path is None:
        outline_path = latest_script(None, script_dir)
        if not outline_path:
            return []

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

        # Skip non-visual sections — no new footage needed.
        if re.match(r"(outro|hook options|cta options)", heading, re.IGNORECASE):
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
            sections.append({"section": heading, "query": query.strip()[:80], "clips_needed": 0, "cue": hint})
            continue

        # Priority 2: script visual cue markers — emit one search job per marker
        # Use findall so every [CLIP: ...] in the section gets its own job; re.search would
        # silently drop all but the first cue, which is the main cause of missed/wrong clips.
        clip_markers = re.findall(r"\[(CLIP|INTERVIEW|GRAPHIC):\s*(.+?)\]", block, re.IGNORECASE)
        if clip_markers:
            for cue_type_raw, cue_raw in clip_markers:
                cue_type = cue_type_raw.lower()
                cue = cue_raw.strip()
                # Strip " — channel" suffix
                cue = re.split(r"\s*[—–-]\s*(?:NHL|Sportsnet|TSN|ESPN|BarDown|placeholder.*)", cue)[0].strip()
                cue = cue.strip("*").strip()
                if re.match(r"^\d{2}-", cue) or "placeholder" in cue.lower():
                    continue
                if subject:
                    subj_words = set(subject.lower().split())
                    cue_words  = set(cue.lower().split())
                    if not (subj_words & cue_words):
                        query = f"{subject} {cue}"
                    else:
                        query = cue
                else:
                    query = cue
                sections.append({
                    "section": f"{heading} ({cue_type})",
                    "query": query.strip()[:80],
                    "clips_needed": 0,
                    # Carry the raw cue so the auto-mode loop can pass it to Claude scoring
                    "cue": cue,
                })
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

        sections.append({"section": heading, "query": query.strip()[:80], "clips_needed": 0, "cue": query.strip()})

    return sections


# ---------------------------------------------------------------------------
# Outline parsing — [CLIP: ...] markers (interactive --from-outline mode)
# ---------------------------------------------------------------------------

def parse_clip_cues_from_outline(outline_path: Path = None, script_dir: Path = SCRIPTED_DIR) -> list[str]:
    """
    Read the latest scripted outline and extract [CLIP: description] markers.
    Returns a list of search query strings, one per clip cue.
    """
    if outline_path is None:
        outline_path = latest_script(None, script_dir)
        if not outline_path:
            return []

    print(f"[gather_clips] Reading clip cues from: {outline_path.name}")
    text = outline_path.read_text(encoding="utf-8")

    raw_cues = re.findall(r"\[(?:CLIP|INTERVIEW|GRAPHIC):\s*(.+?)\]", text, re.IGNORECASE)

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
    channel_ids: list[str] = None,
    max_results: int = 5,
    max_pages: int = 1,
    include_broad: bool = False,
    seen_urls: set[str] = None,
    stop_after: int = None,
    use_highlight_qualifier: bool = True,
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

    # Existing interactive search behavior appends highlight qualifiers.
    # Auto mode passes expanded queries directly.
    search_query = _build_highlight_query(topic) if use_highlight_qualifier else topic
    channel_ids = channel_ids or []
    seen_urls = seen_urls if seen_urls is not None else set()

    results = []
    seen_ids = set()
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        search_scopes = []
        if include_broad:
            search_scopes.append(None)
        search_scopes.extend(channel_ids)

        for channel_id in search_scopes:
            page_token = None
            try:
                for _ in range(max_pages):
                    request = {
                        "q": search_query,
                        "type": "video",
                        "order": "relevance",
                        "maxResults": min(max_results, 50),
                        "part": "snippet",
                    }
                    if channel_id:
                        request["channelId"] = channel_id
                    if page_token:
                        request["pageToken"] = page_token

                    response = youtube.search().list(**request).execute()

                    for item in response.get("items", []):
                        vid_id = item["id"]["videoId"]
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                        if vid_id in seen_ids or url in seen_urls:
                            continue
                        seen_ids.add(vid_id)
                        seen_urls.add(url)

                        snippet = item["snippet"]
                        title = html.unescape(snippet.get("title", ""))

                        preliminary_type = classify_candidate({
                            "title": title,
                            "description": html.unescape(snippet.get("description", "")),
                            "channel": html.unescape(snippet.get("channelTitle", "")),
                        })
                        if preliminary_type in {"gameplay", "talking_head"}:
                            print(f"[gather_clips] Filtered ({preliminary_type}): {title[:60]}")
                            continue

                        results.append({
                            "video_id":     vid_id,
                            "title":        title,
                            "description":  html.unescape(snippet.get("description", "")),
                            "channel":      html.unescape(snippet.get("channelTitle", "")),
                            "published_at": snippet.get("publishedAt", ""),
                            "url":          url,
                            "content_type": preliminary_type,
                        })
                        if stop_after and len(results) >= stop_after:
                            return results

                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break
            except Exception as e:
                scope = channel_id or "broad search"
                print(f"[gather_clips] Search error for {scope}: {e}")
    except Exception as e:
        print(f"[gather_clips] YouTube API error: {e}")

    return results


def search_ytdlp_for_clips(
    topic: str,
    max_results: int = 25,
    seen_urls: set[str] = None,
    stop_after: int = None,
) -> list[dict]:
    """
    Search YouTube through yt-dlp's ytsearch extractor.

    This avoids YouTube Data API quota for demo and local client workflows while
    keeping the same candidate shape as the API search path.
    """
    seen_urls = seen_urls if seen_urls is not None else set()
    limit = max(1, min(max_results, 50))
    cmd = [
        "yt-dlp",
        *_yt_base_cli_flags(),
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        f"ytsearch{limit}:{topic}",
    ]
    results: list[dict] = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"[gather_clips] yt-dlp search failed: {e}")
        return results

    if result.returncode != 0:
        print(f"[gather_clips] yt-dlp search error: {result.stderr[:300]}")
        return results

    for line in result.stdout.splitlines():
        if stop_after and len(results) >= stop_after:
            break
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        vid_id = item.get("id") or ""
        url = item.get("webpage_url") or item.get("url") or ""
        if vid_id and not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={vid_id}"
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = html.unescape(item.get("title") or "")
        channel = html.unescape(item.get("uploader") or item.get("channel") or "")
        description = html.unescape(item.get("description") or "")
        preliminary_type = classify_candidate({
            "title": title,
            "description": description,
            "channel": channel,
        })
        if preliminary_type in {"gameplay", "talking_head"}:
            print(f"[gather_clips] Filtered ({preliminary_type}): {title[:60]}")
            continue

        results.append({
            "video_id": vid_id,
            "title": title,
            "description": description,
            "channel": channel,
            "published_at": item.get("upload_date") or "",
            "url": url,
            "content_type": preliminary_type,
        })

    return results


def search_reddit_for_clips(
    topic: str,
    subreddits: list[str] = None,
    max_results: int = 20,
    seen_urls: set[str] = None,
    stop_after: int = None,
) -> list[dict]:
    """
    Search Reddit for video posts matching the topic.

    Hits Reddit's public JSON search API (no API key needed) and returns
    video post URLs in the same candidate dict shape as the YouTube paths.
    Supported video hosts: v.redd.it (native), Streamable, Clips.Twitch, Medal.
    YouTube links in Reddit posts are skipped (they're already covered by the
    YouTube search path).

    Returns list of dicts: video_id, title, channel, published_at, url, content_type.
    """
    seen_urls = seen_urls if seen_urls is not None else set()
    subreddits = subreddits or ["hockey", "canucks", "nhl"]
    stop_after = stop_after or max_results

    _VIDEO_DOMAINS = {
        "v.redd.it", "streamable.com", "clips.twitch.tv",
        "medal.tv", "clippituser.tv",
    }
    _SKIP_DOMAINS = {"youtube.com", "youtu.be", "twitter.com", "x.com"}

    results: list[dict] = []

    for subreddit in subreddits:
        if subreddit in _REDDIT_BLOCKED_SUBREDDITS:
            continue
        if stop_after and len(results) >= stop_after:
            break
        encoded_topic = urllib.parse.quote(topic)
        api_url = (
            f"https://www.reddit.com/r/{subreddit}/search.json"
            f"?q={encoded_topic}&restrict_sr=true&sort=new&t=month&limit=25&type=link"
        )
        try:
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "DeanerHD/1.0 (hockey clip research)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            if "403" in str(e) or "Blocked" in str(e):
                _REDDIT_BLOCKED_SUBREDDITS.add(subreddit)
                print(f"[gather_clips] Reddit blocked r/{subreddit} public search for this run; continuing with other sources.")
            else:
                print(f"[gather_clips] Reddit search error for r/{subreddit}: {e}")
            continue

        for child in data.get("data", {}).get("children", []):
            if stop_after and len(results) >= stop_after:
                break
            post = child.get("data", {})

            domain = post.get("domain", "")
            is_native_video = post.get("is_video", False)

            # Determine video URL
            video_url = None
            if is_native_video:
                # v.redd.it — use the Reddit post URL, yt-dlp handles the rest
                video_url = post.get("url", "")
            elif any(vd in domain for vd in _VIDEO_DOMAINS):
                video_url = post.get("url", "")

            if not video_url:
                continue
            if any(skip in video_url for skip in _SKIP_DOMAINS):
                continue
            if video_url in seen_urls:
                continue
            seen_urls.add(video_url)

            title = html.unescape(post.get("title", ""))
            preliminary_type = classify_candidate({"title": title, "description": "", "channel": f"r/{subreddit}"})
            if preliminary_type in {"gameplay", "talking_head"}:
                continue

            results.append({
                "video_id": post.get("id", ""),
                "title": title,
                "description": "",
                "channel": f"r/{subreddit}",
                "published_at": str(int(post.get("created_utc", 0))),
                "url": video_url,
                "content_type": preliminary_type,
            })

    return results


def search_web_for_clip_sources(
    topic: str,
    max_results: int = 12,
    seen_urls: set[str] = None,
) -> list[dict]:
    """
    Find hockey clip/article pages outside YouTube.

    This is an internal source-discovery helper: Dean still just asks to gather
    clips, and Codex tries NHL/Sportsnet/TSN/ESPN-style sources in the background.
    yt-dlp will only download sources it supports; unsupported pages are skipped.
    """
    seen_urls = seen_urls if seen_urls is not None else set()
    domains = ["nhl.com", "sportsnet.ca", "tsn.ca", "espn.com/nhl"]
    results: list[dict] = []

    for domain in domains:
        if len(results) >= max_results:
            break
        query = urllib.parse.quote_plus(f"site:{domain} {topic} video")
        url = f"https://duckduckgo.com/html/?q={query}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 DeanerHD clip research"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_text = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        links = re.findall(r'href="[^"]*uddg=([^"&]+)', html_text)
        if not links:
            links = re.findall(r'href="(https?://[^"]+)"', html_text)
        for encoded_link in links:
            if len(results) >= max_results:
                break
            candidate_url = html.unescape(urllib.parse.unquote(encoded_link))
            if not candidate_url.startswith("http") or "duckduckgo.com" in candidate_url:
                continue
            if candidate_url in seen_urls:
                continue
            seen_urls.add(candidate_url)
            title = candidate_url.split("?")[0].rstrip("/").split("/")[-1].replace("-", " ")
            results.append({
                "video_id": "",
                "title": title or candidate_url,
                "description": "",
                "channel": domain,
                "published_at": "",
                "url": candidate_url,
                "content_type": "game",
                "source_provider": "web",
            })

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


def _probe_media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "/opt/homebrew/bin/ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _enforce_downloaded_clip_duration(path: Path) -> bool:
    """
    Verify a downloaded raw clip is 3.0-4.9s. Trim overlong clips in place.
    Returns False for unusably short or unreadable clips.
    """
    duration = _probe_media_duration(path)
    if duration < MIN_CLIP_DURATION:
        print(f"[gather_clips] Downloaded clip too short ({duration:.2f}s) — skipped.")
        try:
            path.unlink()
        except OSError:
            pass
        return False
    if duration <= MAX_CLIP_DURATION:
        return True

    tmp_path = path.with_name(path.stem + "-trimmed" + path.suffix)
    cmd = [
        "/opt/homebrew/bin/ffmpeg", "-y",
        "-i", str(path),
        "-t", f"{MAX_CLIP_DURATION:.1f}",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not tmp_path.exists():
        print(f"[gather_clips] Could not trim overlong clip: {result.stderr[:200]}")
        return False

    tmp_path.replace(path)
    trimmed_duration = _probe_media_duration(path)
    if trimmed_duration < MIN_CLIP_DURATION:
        print(f"[gather_clips] Trimmed clip too short ({trimmed_duration:.2f}s) — skipped.")
        try:
            path.unlink()
        except OSError:
            pass
        return False
    if trimmed_duration > MAX_CLIP_DURATION:
        print(f"[gather_clips] Trimmed clip still too long ({trimmed_duration:.2f}s) — skipped.")
        try:
            path.unlink()
        except OSError:
            pass
        return False
    return True


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
    if end_seconds - start_seconds < MIN_CLIP_DURATION:
        print(f"[gather_clips] Segment too short ({end_seconds - start_seconds:.2f}s) — skipped.")
        return False

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
                return _enforce_downloaded_clip_duration(output_path)

        return output_path.exists() and _enforce_downloaded_clip_duration(output_path)

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
        "content_type":     video.get("content_type", "game"),
        "downloaded_at":    datetime.now(timezone.utc).isoformat(),
        # Kept for backward compatibility with older generated metadata consumers.
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
    Each window is 3–5 seconds (MIN_CLIP_DURATION to MAX_CLIP_DURATION).
    Skips the first INTRO_SKIP_PCT and last OUTRO_SKIP_PCT of the video.
    Enforces MIN_CLIP_GAP_SECONDS between windows so clips from the same video
    are never consecutive footage of each other.
    """
    clip_duration = max(MIN_CLIP_DURATION, min(clip_duration, MAX_CLIP_DURATION))
    action_start  = video_duration * INTRO_SKIP_PCT
    action_end    = video_duration * (1.0 - OUTRO_SKIP_PCT)
    action_range  = action_end - action_start

    if action_range < clip_duration:
        s = max(0.0, action_start)
        e = min(s + clip_duration, video_duration)
        if e - s < MIN_CLIP_DURATION:
            return []
        return [(round(s, 2), round(e, 2))]

    # Space windows by at least MIN_CLIP_GAP_SECONDS apart within this video
    min_step = clip_duration + MIN_CLIP_GAP_SECONDS
    max_possible = max(1, int(action_range / min_step))
    n_clips = min(n_clips, max_possible)

    step = action_range / max(n_clips, 1)
    candidates = []
    for i in range(n_clips):
        s = action_start + i * step
        e = min(s + clip_duration, action_end)
        if e - s >= MIN_CLIP_DURATION:
            candidates.append((round(s, 2), round(e, 2)))

    # Final gap check
    validated = [candidates[0]] if candidates else []
    for start, end in candidates[1:]:
        prev_end = validated[-1][1]
        if start - prev_end >= MIN_CLIP_GAP_SECONDS:
            validated.append((start, end))

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


def readable_clip_filename(
    clip_num: int,
    section: str,
    video: dict,
    fallback_topic: str,
) -> str:
    """
    Build editor-friendly clip names so Dean can skim clips in Finder.

    Format:
      01-section-name-source-title.mp4
    """
    section_slug = slugify(section or fallback_topic)[:34] or "clip"
    title_slug = slugify(video.get("title", "") or fallback_topic)[:42] or "source"
    return f"{clip_num:02d}-{section_slug}-{title_slug}.mp4"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def gather_clips_for_topic(
    topic: str,
    max_clips: int = 6,
    urls: list[str] = None,
    from_outline: bool = False,
    auto: bool = False,
    project=None,
    search_provider: str = "auto",
    section_filter: str = "",
):
    """
    Full pipeline: find videos → select timestamps → download segments → save metadata.

    auto=True  — fully non-interactive; reads outline sections, searches cue by cue,
                 and downloads short clips into the project raw clip folder.
    auto=False — interactive; prompts for timestamps. Enforces 4.9s max.
    """
    raw_clips_dir = project.raw_clips_dir if project else RAW_CLIPS_DIR
    script_dir = project.script_dir if project else SCRIPTED_DIR
    if project:
        write_default_requirements(project, topic)
        print(f"[gather_clips] Project: {project.root}")
    raw_clips_dir.mkdir(parents=True, exist_ok=True)
    urls = list(urls or [])
    slug = slugify(topic)

    # =========================================================================
    # AUTO MODE
    # =========================================================================
    if auto:
        if search_provider == "youtube-api" and not YOUTUBE_API_KEY:
            print("[gather_clips] --search-provider youtube-api requires YOUTUBE_DATA_API_KEY in config/.env.")
            return

        target_dur = get_target_duration()
        total_clips_needed = math.ceil(target_dur / TARGET_CLIP_DURATION) + 2
        print(f"[gather_clips] Target coverage: {target_dur:.1f}s")
        print(f"[gather_clips] Clips needed: {total_clips_needed} (≤{MAX_CLIP_DURATION:.0f}s each)")

        sources = load_clip_sources()
        channel_ids = [
            ch["channel_id"]
            for ch in sources.get("youtube_highlight_channels", [])
            if ch.get("channel_id")
        ]

        # Parse outline sections for context-aware queries
        outline_path = project.script_path if project and from_outline else None
        sections = parse_outline_sections(topic=topic, script_dir=script_dir, outline_path=outline_path)
        if section_filter:
            needle = section_filter.lower()
            sections = [
                s for s in sections
                if needle in f"{s.get('section', '')} {s.get('query', '')} {s.get('cue', '')}".lower()
            ]
            if not sections:
                print(f"[gather_clips] No outline cue matched section filter: {section_filter}")
                return
        if not sections:
            sections = [{"section": "Main", "query": topic, "clips_needed": total_clips_needed}]
        else:
            per_section = math.ceil(total_clips_needed / len(sections))
            for s in sections:
                s["clips_needed"] = per_section
            print(f"[gather_clips] {len(sections)} outline sections → ~{per_section} clips each\n")

        downloaded = 0
        failed_sections = []
        seen_urls: set[str] = set()
        clips_by_source: dict[str, int] = {}
        clips_by_channel: dict[str, int] = {}

        search_jobs = []
        for sec in sections:
            for query in build_query_expansions(sec["query"]):
                search_jobs.append({
                    "section": sec["section"],
                    "query": query,
                    "clips_needed": sec.get("clips_needed", total_clips_needed),
                    # Carry the original cue text for Claude relevance scoring.
                    # The first expansion is the raw cue; subsequent expansions use it too.
                    "cue": sec.get("cue", sec["query"]),
                })
        section_counts: dict[str, int] = {}

        for job in search_jobs:
            if downloaded >= total_clips_needed:
                break
            section_name = job["section"]
            section_limit = int(job.get("clips_needed") or total_clips_needed)
            if section_counts.get(section_name, 0) >= section_limit:
                continue

            query = job["query"]
            relevance_seed = query if from_outline else topic
            topic_keywords = extract_topic_keywords(relevance_seed)
            remaining = min(
                total_clips_needed - downloaded,
                section_limit - section_counts.get(section_name, 0),
            )

            print(f"--- Section: {job['section']}")
            print(f"    Query:   {query}")
            print(f"    Need:    {remaining} more clip(s)")

            candidates = []
            stop_after = max(remaining * 3, 10)
            if search_provider in {"auto", "youtube-api"} and YOUTUBE_API_KEY:
                candidates = search_youtube_for_clips(
                    query,
                    channel_ids,
                    max_results=25,
                    max_pages=2,
                    include_broad=True,
                    seen_urls=seen_urls,
                    stop_after=stop_after,
                    use_highlight_qualifier=False,
                )
            if search_provider in {"auto", "ytdlp"} and len(candidates) < max(4, min(remaining, 8)):
                more_candidates = search_ytdlp_for_clips(
                    query,
                    max_results=35,
                    seen_urls=seen_urls,
                    stop_after=stop_after,
                )
                candidates.extend(more_candidates)

            # Reddit — runs on every query pass; picks up clips that appear on
            # r/hockey and r/canucks before YouTube channels upload them.
            # Streamable / v.redd.it links are fully yt-dlp-compatible.
            reddit_candidates = search_reddit_for_clips(
                query,
                subreddits=["hockey", "canucks", "nhl"],
                max_results=15,
                seen_urls=seen_urls,
                stop_after=stop_after,
            )
            if reddit_candidates:
                print(f"    [Reddit] +{len(reddit_candidates)} candidate(s)")
            candidates.extend(reddit_candidates)

            web_candidates = search_web_for_clip_sources(
                query,
                max_results=8,
                seen_urls=seen_urls,
            )
            if web_candidates:
                print(f"    [Web] +{len(web_candidates)} NHL/Sportsnet/TSN/ESPN candidate(s)")
            candidates.extend(web_candidates)

            if not candidates:
                print("    ✗ No new search results — trying next query.\n")
                continue

            # Claude relevance scoring — batch-score candidates against the specific cue
            # before downloading anything. One Haiku call per batch; cheap and fast.
            cue_for_scoring = job.get("cue") or query
            try:
                from utils.claude_client import score_clip_relevance
                relevance_scores = score_clip_relevance(candidates[:15], cue_for_scoring)
            except Exception as _score_err:
                print(f"    ⚠ Relevance scoring unavailable ({_score_err}) — falling back to keyword filter.")
                relevance_scores = [10.0] * len(candidates)

            scored_candidates = list(zip(candidates, relevance_scores))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)

            # Log scores so the operator can see what Claude thought
            print(f"    Relevance scores (cue: \"{cue_for_scoring[:60]}\"):")
            for _c, _s in scored_candidates[:8]:
                tag = "✓" if _s >= 4 else "✗"
                print(f"      {tag} {_s:.0f}/10  {_c['title'][:60]}")

            for c, relevance_score in scored_candidates:
                if downloaded >= total_clips_needed or section_counts.get(section_name, 0) >= section_limit:
                    break

                if relevance_score < 4:
                    print(f"    ↷ Low relevance ({relevance_score:.0f}/10): {c['title'][:55]}")
                    continue

                if not _matches_topic_keywords(c, topic_keywords):
                    print(f"    ↷ Off-topic (no keyword match): {c['title'][:55]}")
                    continue
                content_type = classify_candidate(c, topic_keywords)
                if content_type in {"reject", "gameplay", "talking_head"}:
                    print(f"    ↷ Rejected ({content_type}): {c['title'][:55]}")
                    continue

                source_url = c["url"]
                clips_already = clips_by_source.get(source_url, 0)
                if clips_already >= CLIPS_PER_VIDEO_MAX:
                    continue

                info = get_video_info(source_url)
                for k, v in c.items():
                    if k not in info or not info.get(k):
                        info[k] = v
                info["content_type"] = content_type

                dur = info.get("duration", 0)
                w   = info.get("width", 0)
                h   = info.get("height", 0)

                if dur < MIN_VIDEO_DURATION:
                    print(f"    ↷ Too short ({dur}s): {info['title'][:55]}")
                    continue
                if w > 0 and h > 0 and h > w:
                    print(f"    ↷ Vertical ({w}×{h}): {info['title'][:55]}")
                    continue

                remaining = min(
                    total_clips_needed - downloaded,
                    section_limit - section_counts.get(section_name, 0),
                )
                clips_from_this = min(CLIPS_PER_VIDEO_MAX - clips_already, remaining)
                windows = pick_clip_windows(dur, TARGET_CLIP_DURATION, clips_from_this)
                if not windows:
                    print(f"    ↷ No valid 3–5s windows: {info['title'][:55]}")
                    continue

                dur_str = f"{int(dur)//60}:{int(dur)%60:02d}"
                print(f"    ✓ {info['title'][:65]}")
                print(f"      Channel: {info['channel']}  |  Type: {content_type}  |  Duration: {dur_str}  |  Taking: {len(windows)} clip(s)")

                for start, end in windows:
                    if downloaded >= total_clips_needed:
                        break

                    # Enforce 3–5s window
                    end = min(start + MAX_CLIP_DURATION, end)
                    if end - start < MIN_CLIP_DURATION:
                        continue

                    clip_num = downloaded + 1
                    out_path = raw_clips_dir / readable_clip_filename(
                        clip_num,
                        job["section"],
                        info,
                        topic,
                    )
                    s_str = f"{int(start)//60}:{int(start)%60:05.2f}"
                    e_str = f"{int(end)//60}:{int(end)%60:05.2f}"
                    print(f"      ↓ Clip {clip_num:02d}: {s_str}–{e_str}  ({end-start:.1f}s)")

                    ok = download_clip_segment(source_url, start, end, out_path)
                    if ok:
                        actual_duration = _probe_media_duration(out_path)
                        save_clip_metadata(out_path, info, start, start + actual_duration, topic, section=job["section"])
                        downloaded += 1
                        section_counts[section_name] = section_counts.get(section_name, 0) + 1
                        clips_by_source[source_url] = clips_by_source.get(source_url, 0) + 1
                        channel = info.get("channel", "Unknown")
                        clips_by_channel[channel] = clips_by_channel.get(channel, 0) + 1
                        size_kb = out_path.stat().st_size // 1024
                        print(f"               ✓ {out_path.name}  ({size_kb} KB)")
                    else:
                        print("               ✗ Download failed.")
                        failed_sections.append(f"{job['section']} clip {clip_num}")
            print()

        total_secs = downloaded * TARGET_CLIP_DURATION
        print("=" * 55)
        print(f"DONE  |  Clips: {downloaded}  |  Sections failed: {len(failed_sections)}")
        print(f"Total clip duration: ~{total_secs:.0f}s  (target: {target_dur:.1f}s)")
        print(f"Distinct source videos: {len(clips_by_source)}")
        if clips_by_source:
            print("Source URL counts:")
            for source_url, count in sorted(clips_by_source.items(), key=lambda item: (-item[1], item[0])):
                print(f"  {count}× {source_url}")
        if clips_by_channel:
            print("Channel counts:")
            for channel, count in sorted(clips_by_channel.items(), key=lambda item: (-item[1], item[0].lower())):
                print(f"  {count}× {channel}")
        if downloaded < total_clips_needed:
            missing = total_clips_needed - downloaded
            print(f"WARNING: Still missing ~{missing} clip(s) for the target coverage.")
        if downloaded:
            print(f"Clips saved to: {raw_clips_dir}")
            print("Review them in that raw folder and use the keepers in Dean's editor.")
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
            info["content_type"] = classify_candidate(info, extract_topic_keywords(topic))
            videos.append(info)
            dur = info["duration"]
            print(f"  ✓ {info['title'][:70]} ({dur//60}:{dur%60:02d}) — {info['channel']}")

    elif from_outline:
        queries = parse_clip_cues_from_outline(script_dir=script_dir)
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
                    info["content_type"] = classify_candidate(info, extract_topic_keywords(q))
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
            print("  Example: python3 scripts/gather_clips.py --topic '...' --urls 'https://youtube.com/watch?v=...'")
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

        # Enforce 4.9s hard cap
        if end - start > MAX_CLIP_DURATION:
            end = start + MAX_CLIP_DURATION
            cap_end_str = f"{int(end)//60}:{int(end)%60:02d}"
            print(f"         ⚠  Capped to {MAX_CLIP_DURATION:.0f}s → end adjusted to {cap_end_str}")

        clip_num = downloaded + 1
        out_path = raw_clips_dir / readable_clip_filename(
            clip_num,
            topic,
            video,
            topic,
        )

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
        print(f"Clips saved to: {raw_clips_dir}")
        print("Review them in that raw folder and use the keepers in Dean's editor.")
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
        "--section", type=str, default="",
        help="Only gather outline cues whose section/query/cue text contains this phrase."
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
    parser.add_argument(
        "--project", type=str, default="",
        help="Optional project slug/path. Uses that package's outline and top-level raw clip folder."
    )
    parser.add_argument(
        "--search-provider",
        choices=("auto", "youtube-api", "ytdlp"),
        default="auto",
        help="Search backend for --auto. ytdlp avoids YouTube Data API quota."
    )
    args = parser.parse_args()
    project = resolve_project(args.project, seed=args.topic or "video", create=bool(args.project))

    if not args.topic and not args.from_outline:
        parser.error("Provide --topic or --from-outline")

    topic = args.topic
    if args.from_outline and not topic:
        script_path = latest_script(project, SCRIPTED_DIR)
        if script_path:
            if project and getattr(project, "simple_layout", False):
                topic = project.slug.replace("-", " ").strip()
            else:
                topic = script_path.stem.replace("-script", "").replace("-", " ").strip()
        else:
            topic = "hockey highlights"

    gather_clips_for_topic(
        topic=topic,
        max_clips=args.max_clips,
        urls=args.urls,
        from_outline=args.from_outline,
        auto=args.auto,
        project=project,
        search_provider=args.search_provider,
        section_filter=args.section,
    )


if __name__ == "__main__":
    main()
