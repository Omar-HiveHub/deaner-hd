"""
analyze_voice.py — Refresh voice/scripts/ from latest transcript corpus
========================================================================
Populates voice/scripts/ with the top N videos by view count so that
generate_outline.py always has the best style examples loaded.

The reference files (tone.md, phrases.md, banned_topics.md) were written
manually from corpus analysis and should be edited directly, not regenerated.

Run AFTER transcribe_channel.py to update style examples with any new videos.

Usage:
    python analyze_voice.py

Outputs:
    voice/_analysis.json            — structured analysis data
    references/tone.md              — sentence style, energy, dos/don'ts
    references/phrases.md           — exact phrases quoted from videos
    references/banned_topics.md     — topics/formats Dean consistently avoids
    voice/scripts/<title-slug>.md   — top 5 videos by view count as style examples
"""

import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT   = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = _PROJECT_ROOT / "voice" / "transcripts"
SCRIPTS_DIR     = _PROJECT_ROOT / "voice" / "scripts"
REFERENCES_DIR  = _PROJECT_ROOT / "references"
ANALYSIS_PATH   = _PROJECT_ROOT / "voice" / "_analysis.json"

load_dotenv(_PROJECT_ROOT / "config" / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("[analyze_voice] ERROR: ANTHROPIC_API_KEY not set in config/.env")
    sys.exit(1)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL  = "claude-sonnet-4-6"

# Max words to include per transcript in the analysis batch (keeps tokens manageable)
TRANSCRIPT_WORD_LIMIT = 600


# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------

def _parse_view_count(text: str) -> int:
    m = re.search(r"^VIEW COUNT:\s*(\d+)", text, re.MULTILINE)
    return int(m.group(1)) if m else 0


def load_all_transcripts() -> list[dict]:
    """
    Load all transcript files from voice/transcripts/.
    Returns list of dicts sorted by view count descending:
      { filename, title, date, view_count, like_count, comment_count, url, transcript_text }
    """
    if not TRANSCRIPTS_DIR.exists():
        return []

    records = []
    for f in TRANSCRIPTS_DIR.glob("*.txt"):
        try:
            raw = f.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[analyze_voice] Could not read {f.name}: {e}")
            continue

        def _field(key: str) -> str:
            m = re.search(rf"^{key}:\s*(.+)", raw, re.MULTILINE)
            return m.group(1).strip() if m else ""

        transcript_match = re.search(r"^TRANSCRIPT:\n(.+)", raw, re.MULTILINE | re.DOTALL)
        transcript_text  = transcript_match.group(1).strip() if transcript_match else ""

        # Truncate transcript to TRANSCRIPT_WORD_LIMIT words for the batch prompt
        words = transcript_text.split()
        truncated = " ".join(words[:TRANSCRIPT_WORD_LIMIT])
        if len(words) > TRANSCRIPT_WORD_LIMIT:
            truncated += " [...]"

        records.append({
            "filename":       f.name,
            "title":          _field("TITLE"),
            "date":           _field("DATE"),
            "view_count":     _parse_view_count(raw),
            "like_count":     _field("LIKE COUNT"),
            "comment_count":  _field("COMMENT COUNT"),
            "url":            _field("URL"),
            "full_text":      raw,
            "transcript_text": truncated,
        })

    return sorted(records, key=lambda r: r["view_count"], reverse=True)


def build_corpus_block(records: list[dict]) -> str:
    """Format truncated transcripts into a single prompt block."""
    blocks = []
    for r in records:
        views = f"{r['view_count']:,}" if r["view_count"] else "N/A"
        blocks.append(
            f"--- VIDEO: {r['title']} | Views: {views} | Date: {r['date']}\n"
            f"{r['transcript_text']}"
        )
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """
You are a voice analyst. You will study transcripts from a YouTube hockey commentary channel
and extract the creator's speech patterns strictly from what appears in the text — no guesses,
no inventions, no general commentary-channel clichés.

Analyse the transcripts and return a JSON object with exactly this structure:

{
  "opening_phrases": [
    // Word-for-word openers you actually see in the transcripts
    // e.g. "Alright, so let's get into it."
  ],
  "transition_phrases": [
    // Exact phrases used between video sections
  ],
  "reactions_and_exclamations": [
    // Reactions to plays, stats, or moments — exact words
  ],
  "sign_off_sequence": [
    // The exact sign-off sequence in order — every step
    // e.g. ["Let me know in the comments.", "Make sure you like, comment, subscribe.", "Peace out and take care."]
  ],
  "recurring_expressions": [
    // Phrases that appear multiple times across videos — distinctly his
  ],
  "sentence_style_notes": [
    // 3–5 observations about sentence length, rhetorical questions, pacing
    // Quote directly from the transcripts to illustrate each point
  ],
  "energy_notes": [
    // 2–3 observations about energy level and when it shifts
  ],
  "things_he_never_says": [
    // Inferred from what is consistently absent — overly formal language,
    // sports clichés, corporate-speak, etc. Be specific.
  ],
  "sample_intro_structure": "A 2–3 sentence description of how he typically opens a video, with a real example quoted",
  "sample_outro_structure": "A 2–3 sentence description of how he closes, with real example quoted",
  "consistently_avoided_topics": [
    // Topics, teams, formats, or story angles that are absent across the entire corpus
  ],
  "off_limit_formats": [
    // Types of videos he never makes (e.g. pure prediction videos, listicle-style, etc.)
  ]
}

Return ONLY the JSON object. No preamble, no explanation, no markdown fences.
"""


def run_analysis(corpus_block: str) -> dict:
    """Send corpus to Claude and return the parsed analysis dict."""
    print("[analyze_voice] Sending transcripts to Claude for voice analysis...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": f"Here are the transcripts:\n\n{corpus_block}"}],
    )
    raw_json = response.content[0].text.strip()

    # Strip markdown fences if Claude adds them anyway
    raw_json = re.sub(r"^```json\s*", "", raw_json)
    raw_json = re.sub(r"^```\s*", "", raw_json)
    raw_json = re.sub(r"\s*```$", "", raw_json)

    return json.loads(raw_json)


# ---------------------------------------------------------------------------
# Reference file writers
# ---------------------------------------------------------------------------

def write_tone_md(analysis: dict) -> None:
    """Write references/tone.md from analysis data."""
    def bullets(items: list) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "_None identified_"

    content = f"""# Tone Guide — Deaner-HD
#
# Generated by analyze_voice.py from full transcript corpus.
# All entries are derived strictly from Dean's actual speech.
# Do not manually edit — re-run analyze_voice.py to regenerate.

---

## Sentence Style

{bullets(analysis.get("sentence_style_notes", []))}

---

## Energy Level

{bullets(analysis.get("energy_notes", []))}

---

## Signature Phrases

See also references/phrases.md for the full phrase list.

{bullets(analysis.get("recurring_expressions", []))}

---

## Things Dean Never Says

{bullets(analysis.get("things_he_never_says", []))}

---

## Sample Intro Structure

{analysis.get("sample_intro_structure", "_Not identified_")}

---

## Sample Outro Structure

{analysis.get("sample_outro_structure", "_Not identified_")}
"""
    (REFERENCES_DIR / "tone.md").write_text(content, encoding="utf-8")
    print("[analyze_voice] Written: references/tone.md")


def write_phrases_md(analysis: dict) -> None:
    """Write references/phrases.md from analysis data."""
    def bullets(items: list) -> str:
        return "\n".join(f'- "{item}"' for item in items) if items else "_None identified_"

    sign_off = analysis.get("sign_off_sequence", [])
    sign_off_block = "\n".join(f"{i+1}. \"{s}\"" for i, s in enumerate(sign_off)) if sign_off else "_Not identified_"

    content = f"""# Phrases — Deaner-HD
#
# Generated by analyze_voice.py from full transcript corpus.
# All phrases are quoted directly from Dean's videos.
# Do not manually edit — re-run analyze_voice.py to regenerate.

---

## Openers

{bullets(analysis.get("opening_phrases", []))}

---

## Transition Phrases

{bullets(analysis.get("transition_phrases", []))}

---

## Reactions / Exclamations

{bullets(analysis.get("reactions_and_exclamations", []))}

---

## Sign-off / Outro Sequence

{sign_off_block}

---

## Recurring Expressions

{bullets(analysis.get("recurring_expressions", []))}
"""
    (REFERENCES_DIR / "phrases.md").write_text(content, encoding="utf-8")
    print("[analyze_voice] Written: references/phrases.md")


def write_banned_topics_md(analysis: dict) -> None:
    """Write references/banned_topics.md from analysis data."""
    def bullets(items: list) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "_None identified_"

    content = f"""# Banned Topics — Deaner-HD
#
# Generated by analyze_voice.py — inferred from what is consistently absent
# across the full transcript corpus. Also includes confirmed rules from DEAN.md.
#
# The AI checks this file when generating ideas and outlines.
# Do not manually edit — re-run analyze_voice.py to regenerate.

---

## Off-Limit Topics / Story Angles

{bullets(analysis.get("consistently_avoided_topics", []))}

Also off-limits (from channel rules):
- Non-hockey sports (no football, basketball, baseball)
- Politically charged non-hockey topics
- Gear reviews or equipment content
- Routine low-stakes games with nothing notable to say

---

## Off-Limit Formats

{bullets(analysis.get("off_limit_formats", []))}

---

## Off-Limit Teams

- No confirmed team restrictions beyond scope (channel now covers full NHL, not Canucks-only)

---

## Off-Limit Players

- No specific player bans — defer to DEAN.md Topics Never Covered section
"""
    (REFERENCES_DIR / "banned_topics.md").write_text(content, encoding="utf-8")
    print("[analyze_voice] Written: references/banned_topics.md")


# ---------------------------------------------------------------------------
# Populate voice/scripts/ with top performers
# ---------------------------------------------------------------------------

def populate_scripts_dir(records: list[dict], top_n: int = 5) -> None:
    """
    Copy the top N videos by view count into voice/scripts/ as style examples.
    These are loaded by claude_client._load_sample_scripts() on every outline call.
    """
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Clear old auto-generated files first (leave any manually written ones)
    for f in SCRIPTS_DIR.glob("*.md"):
        if f.stem.startswith("auto-"):
            f.unlink()

    top = records[:top_n]
    for r in top:
        if not r["title"]:
            continue
        slug = re.sub(r"[^a-z0-9\s-]", "", r["title"].lower())
        slug = re.sub(r"\s+", "-", slug.strip())[:60].strip("-")
        out_path = SCRIPTS_DIR / f"auto-{slug}.md"
        out_path.write_text(r["full_text"], encoding="utf-8")
        views = f"{r['view_count']:,}" if r["view_count"] else "N/A"
        print(f"[analyze_voice] voice/scripts/auto-{slug}.md  ({views} views)")

    print(f"[analyze_voice] {min(len(top), top_n)} style example(s) written to voice/scripts/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    records = load_all_transcripts()
    if not records:
        print("[analyze_voice] No transcripts found in voice/transcripts/")
        print("  Run transcribe_channel.py first.")
        sys.exit(1)

    print(f"[analyze_voice] Found {len(records)} transcript(s). Top 5 by view count:")
    for r in records[:5]:
        views = f"{r['view_count']:,}" if r["view_count"] else "N/A"
        print(f"  {views:>10} views — {r['title'][:65]}")

    corpus_block = build_corpus_block(records)

    # Analyse
    try:
        analysis = run_analysis(corpus_block)
    except json.JSONDecodeError as e:
        print(f"[analyze_voice] Claude returned invalid JSON: {e}")
        print("  Check voice/_analysis_raw.txt for the raw response.")
        sys.exit(1)
    except Exception as e:
        print(f"[analyze_voice] Analysis failed: {e}")
        sys.exit(1)

    # Save raw analysis
    ANALYSIS_PATH.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[analyze_voice] Analysis saved to voice/_analysis.json")

    # Write reference files
    write_tone_md(analysis)
    write_phrases_md(analysis)
    write_banned_topics_md(analysis)

    # Populate voice/scripts/
    populate_scripts_dir(records, top_n=5)

    print("\n[analyze_voice] Done.")
    print("  References updated. Run generate_outline.py to test the output.")


if __name__ == "__main__":
    main()
