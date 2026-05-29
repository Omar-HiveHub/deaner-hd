"""
utils/claude_client.py — Anthropic Claude Wrapper
===================================================
Centralised client for all Claude API calls in the Deaner-HD system.

Models used (per topic type):
  - claude-sonnet-4-6   : default for ideas, incident/general scripts, drafts
  - claude-opus-4-7     : biography/documentary scripts (the 75k-view tier)
                          uses extended thinking for tighter story arcs
  - claude-haiku-4-5    : metadata (titles, description, tags)
                          fast + cheap, same Claude voice as the script

Prompt caching:
  Every Claude call here caches the channel-context system block
  (DEAN.md + tone.md + sample transcripts ≈ 8–12K tokens). 5-minute TTL.
  Within a single video session (ideas → script → metadata) every call
  after the first hits cache → ~90% cost cut + faster response.

Functions exposed to other scripts:
  - load_context_from_dean_md()    : read DEAN.md + reference files as a string
  - generate_ideas(raw_content)    : ranked video topic suggestions in Dean's voice
  - generate_script(topic, ...)    : full ready-to-record voiceover script
  - generate_metadata(script_text) : 3 titles + description + tags
"""

import os
import re
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Local claude CLI binary (authenticated via Claude Code, no API key needed)
_CLAUDE_LOCAL = Path.home() / ".claude" / "local" / "claude"

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / "config" / ".env")

client = anthropic.Anthropic()

# Model routing
SONNET_MODEL   = "claude-sonnet-4-6"
OPUS_MODEL     = "claude-opus-4-7"
HAIKU_MODEL    = "claude-haiku-4-5"

# File paths
DEAN_MD_PATH       = _PROJECT_ROOT / "DEAN.md"
REFERENCE_DIR      = _PROJECT_ROOT / "03_Reference"
LEGACY_REFERENCE_DIR = _PROJECT_ROOT / "references"
TONE_MD_PATH       = REFERENCE_DIR / "channel-notes" / "tone.md"
PHRASES_MD_PATH    = REFERENCE_DIR / "channel-notes" / "phrases.md"
BANNED_TOPICS_PATH = REFERENCE_DIR / "channel-notes" / "banned_topics.md"
TRANSCRIPTS_DIR    = REFERENCE_DIR / "transcripts"


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def load_context_from_dean_md() -> str:
    """
    Read DEAN.md plus all reference files and return combined context string.
    Injected into every Claude prompt as the system-level context.
    """
    try:
        parts = [DEAN_MD_PATH.read_text(encoding="utf-8")]
        for path, label in [
            (TONE_MD_PATH,       "TONE GUIDE"),
            (PHRASES_MD_PATH,    "SIGNATURE PHRASES"),
            (BANNED_TOPICS_PATH, "BANNED TOPICS"),
        ]:
            if path.exists():
                parts.append(f"\n\n---\n## {label}\n{path.read_text(encoding='utf-8')}")
        return "\n".join(parts)
    except FileNotFoundError:
        raise FileNotFoundError(f"DEAN.md not found at {DEAN_MD_PATH}. Fill it in before running.")


def _get_view_count(transcript_path: Path) -> int:
    try:
        text = transcript_path.read_text(encoding="utf-8")
        m = re.search(r"^VIEW COUNT:\s*(\d+)", text, re.MULTILINE)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _get_transcript_title(text: str) -> str:
    m = re.search(r"^TITLE:\s*(.+)", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_transcript_body(text: str) -> str:
    title = _get_transcript_title(text)
    m = re.search(r"^TRANSCRIPT:\s*\n(.+)", text, re.MULTILINE | re.DOTALL)
    body = m.group(1).strip() if m else text.strip()
    return f"[VIDEO: {title}]\n{body}" if title else body


def _classify_transcript(title: str) -> str:
    t = title.lower()
    biography_signals = [
        "greatest", "prospect", "draft", "career", "all time",
        "swedish", "history", "breakdown", "ever seen", "becoming",
        "rebuild", "best ever", "analysis",
    ]
    incident_signals = [
        "leafs", "maple leafs", "worse", "worst", "tough watch",
        "fight", "incident", "menace", "target", "nobody saw",
        "what happens", "keeps getting", "keeps on", "getting worse",
        "done", "blew it", "blowing",
    ]
    if any(kw in t for kw in biography_signals):
        return "biography"
    if any(kw in t for kw in incident_signals):
        return "incident"
    return "general"


def _load_sample_scripts(n: int = 5, topic_type: str = "auto") -> str:
    """
    Load n top-performing transcripts from 03_Reference/transcripts/ as voice examples.
    Sorts by VIEW COUNT so highest-leverage videos anchor the style.
    """
    if not TRANSCRIPTS_DIR.exists():
        return ""

    entries = []
    for f in TRANSCRIPTS_DIR.rglob("*.txt"):
        try:
            text = f.read_text(encoding="utf-8")
            title = _get_transcript_title(text)
            entries.append({
                "path": f,
                "title": title,
                "view_count": _get_view_count(f),
                "type": _classify_transcript(title),
                "text": text,
            })
        except Exception:
            continue

    if not entries:
        return ""

    entries.sort(key=lambda e: e["view_count"], reverse=True)
    selected = []

    if topic_type == "biography":
        top_anchors = entries[:2]
        bio_entries = [e for e in entries if e["type"] == "biography"]
        anchor_paths = {e["path"] for e in top_anchors}
        bio_fill = [e for e in bio_entries if e["path"] not in anchor_paths][:3]
        selected = top_anchors + bio_fill
    elif topic_type == "incident":
        non_bio = [e for e in entries if e["type"] != "biography"]
        selected = non_bio[:n]
        if len(selected) < n:
            remaining = [e for e in entries if e not in selected]
            selected += remaining[:n - len(selected)]
    else:
        selected = entries[:n]

    selected = selected[:n]
    if not selected:
        return ""

    separator = "\n\n" + "=" * 60 + "\n\n"
    return separator.join(_extract_transcript_body(e["text"]) for e in selected)


# ---------------------------------------------------------------------------
# Voice guide — how Dean actually writes and speaks
# ---------------------------------------------------------------------------

_VOICE_GUIDE = """
════════════════════════════════════════════════════════
HOW TO OPEN — choose one pattern based on the topic type
════════════════════════════════════════════════════════

INCIDENT / MOMENT video (a specific play, fight, or event happened):
  "Alright, so [Team] played [Team] today which ended up [score]. [One-sentence recap].
   But something happened which I wanted to shed some light on..."
  → Name the players immediately. No false suspense. Title already told them who — now dig in.

REACTION / DRAMA video (team collapse, shocking move, ongoing saga like Leafs core):
  "Wow, okay, you know what? I've said it before. I'll say it again to all of the
   [fanbase] fans that watch these videos. I am sorry."
  OR: "Wow, okay, you know what? I honestly don't know what to say anymore because..."
  → Lead with the emotional gut-punch first. Explain after.

BIOGRAPHY / DOCUMENTARY video (player deep-dive, prospect breakdown, career story):
  "When you think of [category], what names come to mind?... But what if I told you
   that [subject] might be the most [superlative] of all of them?"
  OR: "Bro, [player name] man, this guy is something else."
  → Question-first to set the frame, then build to the subject.

════════════════════════════════════════════════════════
HOW TO WRITE THE BODY
════════════════════════════════════════════════════════

Chain thoughts with "and," "but," and "I mean" — sentences run directly into each other.
Do NOT start a new paragraph for every thought. Let it flow like spoken word.

Use "I think" and "I feel" before every personal take — never state opinions as facts.
  WRONG: "The Leafs cannot win with this core."
  RIGHT: "I mean, I just don't think this core can win. I feel like we've seen enough at this point."

Use "man" as a mid-sentence intensity marker when the energy builds:
  "But yeah, man, this guy has absolutely taken over." / "You got to respect it, man."

React to your own points immediately. State the thing, then react to what you just said:
  "He scored 8 points in a single game. I mean, 8 points. In one game. [VERIFY] That is not
   something you see in the NCAA. Not at any level at this age."

Short punchy reaction first, longer explanation after:
  "Nuts. But regardless..." / "Crazy stuff." / "Absolute carnage." / "Absolute beauty."

Weave stats into the narrative — never recite them like a report:
  WRONG: "He posted 12 goals, 9 assists for 21 points in 56 games."
  RIGHT: "He put up 12 goals, 9 assists for 21 points in 56 games [VERIFY] which honestly
          isn't that bad when you consider he was playing third-line minutes and not starting
          on the power play."

Keep each thought under roughly 60 words before you pivot or react.
Transition phrases: "But that being said..." / "But yeah, man..." / "After that though..." /
  "And I wanted to point something out..." / "Regardless..." / "I mean, look..."

Ask the audience mid-video at least once:
  "I want to know your thoughts in the comments section below."
  "And I got to ask — what do you guys think about this?"

════════════════════════════════════════════════════════
HOW TO CLOSE — exact sequence, exact words, always in this order
════════════════════════════════════════════════════════

1. Pose a specific question tied to this video's subject:
   "[Specific question]? Let me know in the comments section below."
   OR: "Give me your [thoughts/predictions] in the comments section below."

2. "Thank you so much for watching."
   (sometimes: "Thank you guys so much for watching the video.")

3. "Make sure you like, comment, subscribe if you're new."

4. "And I'll be sure to catch you guys all in the next video."
   OR: "I'll see you in the next one."

5. "Peace out and take care."
   ← ALWAYS exactly these words. ALWAYS last. NEVER changed. NEVER skipped.

════════════════════════════════════════════════════════
WHAT DEAN NEVER SAYS
════════════════════════════════════════════════════════

"In conclusion" / "To summarize" / "First of all, secondly" / "Moving on"
"Let's take a closer look at" / "Breaking it down" / "Let's dive in"
Anything that sounds like it was written and then read off a page
Perfect grammar in long sentences — he talks the way people actually talk
Bullet-point lists read aloud ("Point one... point two... point three...")
Third-person references to himself
Overly dramatic hyperbole — the delivery is opinionated and grounded, not screaming clickbait
"""


# ---------------------------------------------------------------------------
# Internal helpers — caching + response extraction
# ---------------------------------------------------------------------------

def _cached_system_blocks(system_text: str) -> list:
    """
    Return the system field as a list of content blocks with cache_control set
    on the bulk context. Smaller dynamic prefix (if needed later) can stay uncached.

    Anthropic prompt caching: 5-min TTL ephemeral cache, GA since Feb 2026.
    Charges 1.25x on cache write; 0.1x on cache read.
    """
    return [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _text_from_response(response) -> str:
    """
    Extract plain text from a Claude response, skipping any thinking blocks
    that may be present when extended thinking is enabled (Opus biography path).
    """
    parts = []
    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(block.text)
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Public API — generate_ideas
# ---------------------------------------------------------------------------

def generate_ideas(raw_content: str) -> str:
    """
    Given a block of raw content (news headlines, Reddit posts, video titles),
    generate ranked video topic suggestions with hooks in Dean's voice.
    Uses Sonnet 4.6 with prompt caching on the channel context.
    """
    try:
        context = load_context_from_dean_md()
        system_text = f"""You are a YouTube content strategist for a hockey commentary channel.
Here is everything you need to know about the channel and its host:

{context}

Your job is to scan current hockey news and generate ranked video topic ideas
that fit this channel's voice, niche, and style. Filter out anything that
matches the banned topics list. Focus on timeliness and Dean's unique angle.
"""
        user_message = f"""Here is the current hockey news and trending content:

{raw_content}

Generate 5–8 ranked video topic ideas. For each one, include:
1. Suggested video title
2. Opening hook line (first sentence Dean would say on camera)
3. Why it's timely right now (1–2 sentences)
4. Suggested angle (e.g. hot take, breakdown, reaction, stat deep dive)

Format as a numbered markdown list. Put the best idea first.
"""
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=2048,
            system=_cached_system_blocks(system_text),
            messages=[{"role": "user", "content": user_message}],
        )
        return _text_from_response(response)
    except Exception as e:
        print(f"[claude_client] generate_ideas error: {e}")
        raise


# ---------------------------------------------------------------------------
# Public API — generate_script
# ---------------------------------------------------------------------------

def generate_script(topic: str, hook: str = "", topic_type: str = "auto", output_format: str = "outline") -> str:
    """
    Generate a Dean-ready outline or complete voiceover script.

    Routing:
      topic_type == "biography" → Opus 4.7 with extended thinking (premium tier)
      topic_type in ("incident", "general", "auto") → Sonnet 4.6

    The system prompt (channel context + voice guide + 5 sample transcripts)
    is cached, so back-to-back calls within 5 minutes hit cache.
    """
    try:
        context        = load_context_from_dean_md()
        sample_scripts = _load_sample_scripts(n=5, topic_type=topic_type)

        outline_mode = output_format != "script"
        product_label = "outline" if outline_mode else "script"

        system_text = f"""You are writing a DeanerHD {product_label} in the exact speaking voice and workflow style of Dean Tsamis (DeanerHD on YouTube) — a hockey commentary creator with 400+ videos and a deeply consistent on-camera voice.

Dean normally records from rough outlines, not polished teleprompter copy. The default deliverable should help him improvise naturally: strong hooks, section beats, searchable visual cues, fact-check notes, and CTA options. Only write word-for-word prose when the caller explicitly asks for `output_format="script"`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For outline mode, use this exact structure:

# Outline: [working title]

## Hook Options
1. Three punchy Dean-style hook lines, each one sentence.

## Section 1: [short beat name]
[CLIP: searchable real-game visual, include players/teams/event]
- 3-5 Dean-style talking beats he can improvise from.
- Include [VERIFY: claim or stat] next to any claim that needs fact checking.

Repeat 4-6 sections total. Use [INTERVIEW:] and [GRAPHIC:] cues where relevant.

## CTA Options
- 3 specific comment questions tied to the video subject.
- Include Dean's locked ending sequence as a reminder, not as scripted narration.

For script mode, write continuous prose in Dean's speaking voice. No bullet lists in spoken content.
Use these production markers as standalone lines Dean reads around — do not narrate them. Make them precise because the clip gatherer searches YouTube from these cues after the outline/script is approved:
  [CLIP: searchable real-game visual, include players/teams/event]
  [INTERVIEW: searchable player/coach/media interview cue if relevant]
  [GRAPHIC: scorecard/stat/ranking/screenshot cue to hold longer than action]
  [VERIFY: claim or stat]       ← Dean fact-checks this before recording

Target for outline mode: enough beats for a 4–6 minute recording without forcing a word-for-word read.
Target for script mode: 500–700 words of spoken content (4–6 minutes at Dean's natural pace).
Do not write subscribe/like callouts, creator intro screens, or "full clip coming up"
language. The edit should feel like Dean's normal commentary, not a template.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEAN'S VOICE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{_VOICE_GUIDE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANNEL CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAMPLE TRANSCRIPTS — study these and match this voice exactly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{sample_scripts if sample_scripts else "(No samples available — rely on the voice rules above.)"}
"""

        if outline_mode:
            user_message = f"""Write a Dean-ready recording outline for a video about:

Topic: {topic}
{"Opening hook direction: " + hook if hook else ""}
Video type: {topic_type}

Use the kickoff-call workflow: Dean picks a topic, reviews an outline, gathers clips from precise cues, then records from the outline in his own voice.
Do not write a full word-for-word script. Give him hooks, section beats, clip/search cues, stat/graphic cues, verification notes, and CTA options.
The outline must still sound like Dean's thinking style: conversational, direct, measured, and hockey-specific.
"""
        else:
            user_message = f"""Write a complete voiceover-ready script for a video about:

Topic: {topic}
{"Opening hook: " + hook if hook else ""}
Video type: {topic_type}

Write in Dean's voice exactly as it sounds in the sample transcripts.
Start with the appropriate opener for this video type.
End with the exact 5-step sign-off sequence (peace out and take care).
Do not use bullet points or section headers anywhere in the spoken content.
"""

        # Route by topic type
        if topic_type == "biography":
            # Opus 4.7 with extended thinking — better story arcs for the 75k-view tier
            print(f"[claude_client] Routing biography {product_label} → Opus 4.7 (premium tier)")
            response = client.messages.create(
                model=OPUS_MODEL,
                max_tokens=8192,
                thinking={"type": "enabled", "budget_tokens": 6000},
                system=_cached_system_blocks(system_text),
                messages=[{"role": "user", "content": user_message}],
            )
        else:
            print(f"[claude_client] Routing {topic_type} {product_label} → Sonnet 4.6")
            response = client.messages.create(
                model=SONNET_MODEL,
                max_tokens=4096,
                system=_cached_system_blocks(system_text),
                messages=[{"role": "user", "content": user_message}],
            )

        return _text_from_response(response)

    except Exception as e:
        print(f"[claude_client] generate_script error: {e}")
        raise


# ---------------------------------------------------------------------------
# Public API — generate_metadata (replaces Gemini Flash Lite path)
# ---------------------------------------------------------------------------

def generate_metadata(script_or_summary: str, video_filename: str = "") -> str:
    """
    Generate YouTube metadata (titles, description, tags) in Dean's voice.

    Uses Haiku 4.5 — fast, cheap, same Claude voice family as the script,
    so titles and description don't drift in tone vs the spoken voiceover.

    Args:
        script_or_summary: The script text or transcript snippet describing the video.
        video_filename:    Optional filename for topic context.

    Returns:
        Formatted metadata string with TITLE OPTIONS / DESCRIPTION / TAGS sections.
    """
    try:
        context = load_context_from_dean_md()

        system_text = f"""You are writing YouTube metadata for the DeanerHD hockey commentary channel.
The titles, description, and tags must match Dean's actual on-camera voice and the
title patterns that have produced his biggest hits.

Channel context:
{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEAN'S TITLE PATTERNS — these have hit 60k–190k views
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mystery / open-loop:
  "Nobody saw what Tkachuk did to Connor Bedard RIGHT here..."
  "You NEED to hear what Marchand just said about Leafs Fans..."
  "THIS is what happens when you're the NHL's BIGGEST Target..."

Question-frame superlative (biography tier):
  "This player is becoming the GREATEST Swedish Prospect of all time...."
  "Will Shane Wright be BETTER Than Cole Caufield?"

Emotional reaction:
  "It just keeps on getting WORSE for the leafs..."
  "This was a tough watch for Leafs fans…"
  "You HAVE to feel bad for him at this point...."

Common signals across all winners:
  - SELECTIVE caps on 1–2 emotional words (not every word)
  - Ellipsis "..." at the end (creates open loop)
  - Player or team name in the title (not generic)
  - Hints at the surprise without spoiling it
  - 50–70 characters typical
"""

        summary_section = (
            f"\n\nVideo content (script or summary):\n{script_or_summary[:3000]}"
            if script_or_summary
            else (f"\n\nVideo filename hint: {video_filename}" if video_filename else "")
        )

        user_message = f"""Generate YouTube metadata for this video in Dean's voice and style.{summary_section}

Output exactly this format:

## TITLE OPTIONS

Three titles, each on its own line. Vary the angle:
1. Mystery / open-loop (uses "...", hints at a surprise without spoiling)
2. Strong-opinion / hot take (states a position, no clickbait)
3. Specificity / SEO (player name + concrete event)

Each title: 50–70 characters. SELECTIVE caps on 1–2 emotional words only.

## DESCRIPTION

~180–220 words. First two lines are the hook (shown before "more" on YouTube — make them work as a standalone tease). Summarize what the video covers without giving away the surprise. Include 2–3 chapters: [0:00 – Intro], [1:30 – Main Point], [4:00 – Take]. End with: "Make sure you like, comment, subscribe if you're new. Peace out and take care." Add 2–3 hashtags at the bottom.

## TAGS

20–30 tags as a single comma-separated line. Mix: specific (player names, team names, season) + broad (NHL, hockey, Canucks, hockey commentary). No duplicates."""

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2048,
            system=_cached_system_blocks(system_text),
            messages=[{"role": "user", "content": user_message}],
        )
        return _text_from_response(response)

    except Exception as e:
        print(f"[claude_client] generate_metadata error: {e}")
        raise


# ---------------------------------------------------------------------------
# Public API — score_clip_relevance
# ---------------------------------------------------------------------------

def score_clip_relevance(candidates: list[dict], cue_description: str) -> list[float]:
    """
    Score a batch of clip candidates (0-10) against a specific clip cue.

    Uses keyword-overlap scoring: counts how many meaningful words from the cue
    appear in each video's title, description, channel, URL, and source fields.
    Words are weighted by type:
      - Event terms (worlds, iihf, championship, quarterfinal, injury, ejected…) → 3pts
      - Action terms (hit, fight, goal, replay, bench, reaction…) → 2pts
      - General nouns (player names already extracted by caller) → 1pt

    No API key or subprocess needed — deterministic and fast.

    Args:
        candidates: List of dicts with title/description/channel/url/source keys.
        cue_description: The exact [CLIP: ...] cue text from the outline.

    Returns:
        List of float scores (0–10), one per candidate, in input order.
    """
    if not candidates:
        return []

    _EVENT_TERMS = {
        "worlds", "world", "iihf", "championship", "quarterfinal", "semifinal",
        "final", "tournament", "international", "olympics", "olympic",
        "injury", "injured", "ejected", "ejection", "suspension", "suspended",
        "penalty", "banned", "misconduct",
    }
    _ACTION_TERMS = {
        "hit", "fight", "goal", "replay", "reaction", "bench", "response",
        "knockout", "knocked", "dirty", "brutal", "illegal", "cheap",
        "highlights", "highlight", "moment", "collision",
    }

    def _score_one(candidate: dict) -> float:
        searchable_text = " ".join(
            str(candidate.get(key, ""))
            for key in ("title", "description", "channel", "url", "source_provider", "content_type")
        ).lower()
        searchable_words = set(re.sub(r"[^\w\s]", " ", searchable_text).split())
        cue_words = re.sub(r"[^\w\s]", " ", cue_description.lower()).split()
        cue_words = [w for w in cue_words if len(w) >= 3]

        raw = 0.0
        max_possible = 0.0
        for w in cue_words:
            if w in _EVENT_TERMS:
                max_possible += 3
                if w in searchable_words or w in searchable_text:
                    raw += 3
            elif w in _ACTION_TERMS:
                max_possible += 2
                if w in searchable_words or w in searchable_text:
                    raw += 2
            else:
                max_possible += 1
                if w in searchable_words or w in searchable_text:
                    raw += 1

        if max_possible == 0:
            return 5.0
        ratio = raw / max_possible
        # Scale: 0 overlap → 0, full overlap → 10, partial scaled in between
        return round(min(10.0, ratio * 10.0), 1)

    return [_score_one(c) for c in candidates]


# ---------------------------------------------------------------------------
# Legacy alias — keeps existing callers working
# ---------------------------------------------------------------------------

def generate_outline(topic: str, hook: str = "", topic_type: str = "auto") -> str:
    """Generate Dean's preferred hook + section-beat outline."""
    return generate_script(topic, hook=hook, topic_type=topic_type, output_format="outline")
