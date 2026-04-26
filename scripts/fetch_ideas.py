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

import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv

import feedparser
import requests  # for Reddit JSON scraping

# YouTube Data API — used to check competitor channels
from googleapiclient.discovery import build  # pip install google-api-python-client

from utils.claude_client import generate_ideas

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
    for feed in rss_feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            # TODO: filter by date, extract fields, append to results
            pass
        except Exception as e:
            print(f"[fetch_ideas] RSS error for {feed['name']}: {e}")
    return results


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
            # TODO: parse JSON and extract posts
            pass
        except Exception as e:
            print(f"[fetch_ideas] Reddit error for {source['name']}: {e}")
    return results


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
    if not YOUTUBE_API_KEY:
        print("[fetch_ideas] No YOUTUBE_DATA_API_KEY — skipping competitor check")
        return []

    results = []
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        for competitor in competitors:
            try:
                # TODO: query YouTube API for recent uploads from this channel
                pass
            except Exception as e:
                print(f"[fetch_ideas] YouTube API error for {competitor.get('name')}: {e}")
    except Exception as e:
        print(f"[fetch_ideas] YouTube API setup error: {e}")
    return results


# ---------------------------------------------------------------------------
# Content assembly + AI call
# ---------------------------------------------------------------------------

def assemble_raw_content(rss_items: list, reddit_posts: list, competitor_videos: list) -> str:
    """
    Combine all sourced content into a single text block for Claude.
    """
    sections = []

    if rss_items:
        lines = ["## NHL News"]
        for item in rss_items:
            lines.append(f"- [{item.get('title', '')}]({item.get('link', '')})")
            if item.get("summary"):
                lines.append(f"  {item['summary'][:200]}")
        sections.append("\n".join(lines))

    if reddit_posts:
        lines = ["## Reddit Trending"]
        for post in reddit_posts:
            lines.append(f"- [{post.get('title', '')}] ({post.get('score', 0)} upvotes, r/{post.get('subreddit', '')})")
        sections.append("\n".join(lines))

    if competitor_videos:
        lines = ["## Competitors Recently Uploaded"]
        for vid in competitor_videos:
            lines.append(f"- {vid.get('title', '')} — {vid.get('channel', '')}")
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
        competitor_videos = check_competitor_uploads(competitors)
        raw_content = assemble_raw_content(rss_items, reddit_posts, competitor_videos)

    print("[fetch_ideas] Sending to Claude for idea generation...")
    try:
        ideas_markdown = generate_ideas(raw_content)
    except Exception as e:
        print(f"[fetch_ideas] Claude API error: {e}")
        return

    save_ideas(ideas_markdown, IDEAS_OUTPUT_DIR)
    print("[fetch_ideas] Done. Check pipeline/ideas/ for today's suggestions.")


if __name__ == "__main__":
    main()
