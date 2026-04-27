"""
fetch_ideas.py — Topic Idea Generator
======================================
Full workflow:
  1. Load feed URLs from config/feeds.json
  2. Poll each RSS feed using feedparser — collect titles, summaries, links
  3. Scrape Reddit r/hockey and r/canucks hot posts via JSON API
  4. Check competitor YouTube channels for recent uploads using YouTube Data API
  5. Deduplicate and rank by recency
  6. Pass the combined content to Claude Sonnet via claude_client.generate_ideas()
  7. Claude returns 5–8 ranked video topic suggestions with hooks
  8. Save output to pipeline/ideas/YYYY-MM-DD-ideas.md

Run:
    python fetch_ideas.py

Output:
    pipeline/ideas/2026-04-04-ideas.md  (date-stamped)
"""

import calendar
import os
import json
import datetime
import re
from email.utils import parsedate_to_datetime
from pathlib import Path
from dotenv import load_dotenv

import feedparser
import requests  # for Reddit JSON scraping

# YouTube Data API — used to check competitor channels
from googleapiclient.discovery import build  # pip install google-api-python-client

# ---------------------------------------------------------------------------
# Config and paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_DATA_API_KEY")
FEEDS_CONFIG = _PROJECT_ROOT / "config" / "feeds.json"
IDEAS_OUTPUT_DIR = _PROJECT_ROOT / "pipeline" / "ideas"
COMPETITORS_CONFIG = _PROJECT_ROOT / "config" / "competitors.json"

TODAY = datetime.date.today().isoformat()
NOW_UTC = datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Feed polling
# ---------------------------------------------------------------------------

def load_feeds() -> dict:
    """
    Load the feeds configuration from config/feeds.json.

    Returns:
        Parsed dict with keys: youtube_channels, rss_feeds, reddit.

    TODO:
        - Read and parse feeds.json
        - Validate required keys exist
        - Return dict
    """
    with open(FEEDS_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def poll_rss_feeds(rss_feeds: list[dict]) -> list[dict]:
    """
    Poll each RSS feed and return a flat list of recent articles.

    Args:
        rss_feeds: List of feed dicts from feeds.json (each has name, url, notes).

    Returns:
        List of dicts, each with keys: title, link, summary, source, published.

    TODO:
        - Loop through rss_feeds
        - Call feedparser.parse(feed["url"]) for each
        - Extract entries: title, link, summary, published
        - Limit to entries from the last 48 hours
        - Return flat list sorted by published date descending
    """
    results = []
    max_age_hours = 96
    for feed in rss_feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[: feed.get("limit", 20)]:
                published_dt = _entry_datetime(entry)
                if published_dt and _age_hours(published_dt) > feed.get("max_age_hours", max_age_hours):
                    continue
                results.append({
                    "title": _clean_text(entry.get("title", "")),
                    "link": entry.get("link", ""),
                    "summary": _clean_text(entry.get("summary", "")),
                    "source": feed.get("name", ""),
                    "published": published_dt.isoformat() if published_dt else entry.get("published", ""),
                })
        except Exception as e:
            print(f"[fetch_ideas] RSS error for {feed['name']}: {e}")
    return sorted(results, key=lambda item: item.get("published", ""), reverse=True)


def scrape_reddit(reddit_sources: list[dict], limit: int = 25) -> list[dict]:
    """
    Fetch hot posts from Reddit subreddits using the public JSON API.

    Args:
        reddit_sources: List of Reddit source dicts from feeds.json.
        limit:          Number of posts to fetch per subreddit.

    Returns:
        List of dicts with keys: title, url, score, subreddit, num_comments.

    TODO:
        - For each source, GET {url} with a browser-like User-Agent header
        - Parse response JSON — posts are under data.children
        - Extract: title, url, score, subreddit, num_comments
        - Filter out link posts (only text/discussion posts)
        - Return flat list sorted by score descending
    """
    results = []
    headers = {"User-Agent": "Deaner-HD/1.0 (youtube automation, contact via channel)"}
    for source in reddit_sources:
        try:
            resp = requests.get(source["url"], headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                title = _clean_text(post.get("title", ""))
                if not title or post.get("stickied"):
                    continue
                created = datetime.datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=datetime.timezone.utc
                )
                results.append({
                    "title": title,
                    "url": post.get("url_overridden_by_dest") or f"https://reddit.com{post.get('permalink', '')}",
                    "permalink": f"https://reddit.com{post.get('permalink', '')}",
                    "score": int(post.get("score") or 0),
                    "subreddit": post.get("subreddit", source.get("name", "")),
                    "num_comments": int(post.get("num_comments") or 0),
                    "created": created.isoformat(),
                })
        except Exception as e:
            print(f"[fetch_ideas] Reddit error for {source['name']}: {e}")
    return sorted(results, key=lambda post: (post.get("score", 0), post.get("num_comments", 0)), reverse=True)


def check_youtube_channels(channels: list[dict], hours: int = 96, max_results: int = 5) -> list[dict]:
    """
    Check recent uploads from configured YouTube channels.
    """
    if not YOUTUBE_API_KEY:
        print("[fetch_ideas] No YOUTUBE_DATA_API_KEY — skipping YouTube checks")
        return []

    results = []
    published_after = (NOW_UTC - datetime.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        for channel in channels:
            try:
                channel_id = channel.get("channel_id") or resolve_channel_id(youtube, channel)
                if not channel_id:
                    continue
                request = youtube.search().list(
                    part="snippet",
                    channelId=channel_id,
                    type="video",
                    order="date",
                    maxResults=max_results,
                    publishedAfter=published_after,
                )
                response = request.execute()
                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    video_id = item.get("id", {}).get("videoId")
                    if not video_id:
                        continue
                    results.append({
                        "title": _clean_text(snippet.get("title", "")),
                        "channel": snippet.get("channelTitle") or channel.get("name", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "video_url": f"https://www.youtube.com/watch?v={video_id}",
                        "niche": channel.get("niche") or channel.get("notes", ""),
                    })
            except Exception as e:
                print(f"[fetch_ideas] YouTube API error for {channel.get('name')}: {e}")
    except Exception as e:
        print(f"[fetch_ideas] YouTube API setup error: {e}")
    return sorted(results, key=lambda item: item.get("published_at", ""), reverse=True)


def check_competitor_uploads(competitors: list[dict]) -> list[dict]:
    """
    Check recent video uploads from competitor YouTube channels.

    Used to spot trending topics and gaps — if a competitor just posted
    about something, it's timely; we can cover it with Dean's angle.

    Args:
        competitors: List of competitor dicts from competitors.json
                     (each has name, url, niche).

    Returns:
        List of dicts with keys: title, channel, published_at, video_url.

    TODO:
        - Build YouTube Data API client using YOUTUBE_API_KEY
        - For each competitor, extract channel ID from url or search by name
        - Call search.list(channelId=..., order=date, maxResults=5)
        - Return videos published in the last 72 hours
    """
    return check_youtube_channels(competitors, hours=168, max_results=4)


def resolve_channel_id(youtube, channel: dict) -> str:
    """Resolve a YouTube channel ID from a configured URL/handle/name."""
    url = channel.get("url", "")
    handle_match = re.search(r"youtube\.com/@([^/?]+)", url)
    if handle_match:
        try:
            response = youtube.channels().list(
                part="id",
                forHandle=handle_match.group(1),
            ).execute()
            items = response.get("items", [])
            if items:
                return items[0].get("id", "")
        except Exception:
            pass

    response = youtube.search().list(
        part="snippet",
        q=channel.get("name", ""),
        type="channel",
        maxResults=1,
    ).execute()
    items = response.get("items", [])
    return items[0].get("snippet", {}).get("channelId", "") if items else ""


def fetch_nhl_schedule_context(config: dict) -> list[dict]:
    """Fetch upcoming schedule context from the public NHL web API."""
    results = []
    nhl_api = config.get("nhl_api", {})
    teams = nhl_api.get("teams", ["VAN"])
    for team in teams:
        try:
            resp = requests.get(
                f"https://api-web.nhle.com/v1/club-schedule/{team}/week/now",
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()
            for game in data.get("games", []):
                game_date = game.get("gameDate", "")
                away = game.get("awayTeam", {}).get("abbrev", "")
                home = game.get("homeTeam", {}).get("abbrev", "")
                state = game.get("gameState", "")
                results.append({
                    "team": team,
                    "date": game_date,
                    "matchup": f"{away} at {home}",
                    "state": state,
                    "venue": game.get("venue", {}).get("default", ""),
                })
        except Exception as e:
            print(f"[fetch_ideas] NHL schedule error for {team}: {e}")
    return results


# ---------------------------------------------------------------------------
# Content assembly + AI call
# ---------------------------------------------------------------------------

def assemble_raw_content(
    rss_items: list,
    reddit_posts: list,
    youtube_videos: list,
    competitor_videos: list,
    schedule_items: list,
) -> str:
    """
    Combine all sourced content into a single text block for Claude.
    """
    sections = []

    if rss_items:
        lines = ["## NHL News"]
        for item in rss_items[:40]:
            lines.append(f"- [{item.get('title', '')}]({item.get('link', '')}) — {item.get('source', '')}")
            if item.get("summary"):
                lines.append(f"  {item['summary'][:200]}")
        sections.append("\n".join(lines))

    if reddit_posts:
        lines = ["## Reddit Trending"]
        for post in reddit_posts[:40]:
            lines.append(f"- [{post.get('title', '')}] ({post.get('score', 0)} upvotes, r/{post.get('subreddit', '')})")
        sections.append("\n".join(lines))

    if youtube_videos:
        lines = ["## Official/News YouTube Uploads"]
        for vid in youtube_videos[:40]:
            lines.append(f"- [{vid.get('title', '')}]({vid.get('video_url', '')}) — {vid.get('channel', '')}")
        sections.append("\n".join(lines))

    if competitor_videos:
        lines = ["## Competitors Recently Uploaded"]
        for vid in competitor_videos[:40]:
            lines.append(f"- [{vid.get('title', '')}]({vid.get('video_url', '')}) — {vid.get('channel', '')}")
        sections.append("\n".join(lines))

    if schedule_items:
        lines = ["## Schedule Context"]
        for item in schedule_items:
            lines.append(f"- {item.get('date', '')}: {item.get('matchup', '')} ({item.get('state', '')})")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No content fetched."


def save_ideas(ideas_markdown: str, output_dir: Path) -> Path:
    """
    Save the AI-generated ideas to a dated markdown file in pipeline/ideas/.

    Args:
        ideas_markdown: Markdown string returned by Claude.
        output_dir:     Path to pipeline/ideas/.

    Returns:
        Path to the saved file.

    TODO:
        - Build filename: YYYY-MM-DD-ideas.md
        - Write file with a header including date and source summary
        - Return Path object to the saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{TODAY}-ideas.md"
    header = f"# Video Ideas — {TODAY}\n\n"
    try:
        output_path.write_text(header + ideas_markdown, encoding="utf-8")
        print(f"[fetch_ideas] Ideas saved to {output_path}")
    except Exception as e:
        print(f"[fetch_ideas] Error saving ideas: {e}")
        raise
    return output_path


def save_source_report(raw_content: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{TODAY}-source-report.md"
    header = f"# Source Report — {TODAY}\n\nGenerated before AI ranking so Dean can see what was checked.\n\n"
    output_path.write_text(header + raw_content, encoding="utf-8")
    print(f"[fetch_ideas] Source report saved to {output_path}")
    return output_path


def _entry_datetime(entry) -> datetime.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.datetime.fromtimestamp(calendar.timegm(parsed), tz=datetime.timezone.utc)
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt.astimezone(datetime.timezone.utc)
            except Exception:
                continue
    return None


def _age_hours(dt: datetime.datetime) -> float:
    return (NOW_UTC - dt.astimezone(datetime.timezone.utc)).total_seconds() / 3600


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """
    Orchestrates the full idea-fetching pipeline.

    Pass --content <file_path> to skip live scraping and feed a text file
    directly to Claude. Useful for testing or when using transcript files
    as source material instead of RSS/Reddit.

    Example:
        python fetch_ideas.py --content ../voice/transcripts/20260308-bS6KHGnewJI.txt
    """
    import argparse
    parser = argparse.ArgumentParser(description="Fetch and generate video topic ideas.")
    parser.add_argument(
        "--content",
        type=str,
        default="",
        help="Path to a text file to use as raw content instead of live scraping."
    )
    parser.add_argument(
        "--sources-only",
        action="store_true",
        help="Fetch sources and save a source report without calling Claude."
    )
    args = parser.parse_args()

    print("[fetch_ideas] Starting idea fetch...")

    if args.content:
        content_path = Path(args.content)
        if not content_path.exists():
            print(f"[fetch_ideas] --content file not found: {content_path}")
            return
        raw_content = content_path.read_text(encoding="utf-8")
        print(f"[fetch_ideas] Using content from file: {content_path.name} ({len(raw_content):,} chars)")
    else:
        try:
            feeds = load_feeds()
        except Exception as e:
            print(f"[fetch_ideas] Failed to load feeds.json: {e}")
            return

        try:
            with open(COMPETITORS_CONFIG, "r", encoding="utf-8") as f:
                competitors = json.load(f)
        except Exception:
            competitors = []

        rss_items = poll_rss_feeds(feeds.get("rss_feeds", []))
        reddit_posts = scrape_reddit(feeds.get("reddit", []))
        youtube_videos = check_youtube_channels(feeds.get("youtube_channels", []))
        competitor_videos = check_competitor_uploads(competitors)
        schedule_items = fetch_nhl_schedule_context(feeds)
        raw_content = assemble_raw_content(
            rss_items,
            reddit_posts,
            youtube_videos,
            competitor_videos,
            schedule_items,
        )

    if args.sources_only:
        save_source_report(raw_content, IDEAS_OUTPUT_DIR)
        print("[fetch_ideas] Done (sources only).")
        return

    print("[fetch_ideas] Sending to Claude for idea generation...")
    try:
        from utils.claude_client import generate_ideas
        ideas_markdown = generate_ideas(raw_content)
    except Exception as e:
        print(f"[fetch_ideas] Claude API error: {e}")
        return

    save_ideas(ideas_markdown, IDEAS_OUTPUT_DIR)
    print("[fetch_ideas] Done. Check pipeline/ideas/ for today's suggestions.")


if __name__ == "__main__":
    main()
