"""
utils/gemini_client.py — Gemini API Wrapper
============================================
Centralised client for all Google Gemini calls in the Deaner-HD system.

Supports two models:
  - gemini-2.5-flash        : used for heavy tasks (video analysis, moment detection)
  - gemini-2.5-flash-lite   : used for lightweight text tasks (metadata generation)

Functions exposed to other scripts:
  - analyze_video()     : upload a video file and run a prompt against it
  - transcribe_audio()  : extract a transcript from an audio/video file
  - generate_text()     : standard text prompt, no media
  - detect_moments()    : find Short-worthy moments in a finished video,
                          returns structured JSON list

All functions load the API key from the project-root .env file.
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

# Walk up from this file to find the project root .env
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / "config" / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise EnvironmentError(
        "GEMINI_API_KEY not found. Copy config/.env.example to config/.env and fill in your key."
    )

genai.configure(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# Model handles
# ---------------------------------------------------------------------------

FLASH_MODEL = "gemini-2.5-flash"
FLASH_LITE_MODEL = "gemini-2.5-flash-lite"


def _get_model(lite: bool = False) -> genai.GenerativeModel:
    """Return the appropriate GenerativeModel instance."""
    model_name = FLASH_LITE_MODEL if lite else FLASH_MODEL
    return genai.GenerativeModel(model_name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_video(video_path: str, prompt: str) -> str:
    """
    Upload a video file to Gemini and run a prompt against it.

    Used for: understanding video content, summarising games, pulling context
    for outline generation.

    Args:
        video_path: Absolute or relative path to the video file.
        prompt:     The instruction/question to ask about the video.

    Returns:
        The model's text response as a string.

    TODO:
        - Upload video using genai.upload_file()
        - Poll for upload status until state == ACTIVE
        - Call model.generate_content([video_file, prompt])
        - Return response.text
        - Handle upload errors, unsupported formats, and file-size limits
    """
    model = _get_model(lite=False)
    video_file = genai.upload_file(video_path)
    # Poll until the file is ready
    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = genai.get_file(video_file.name)
    if video_file.state.name != "ACTIVE":
        raise RuntimeError(f"File upload failed with state: {video_file.state.name}")
    response = model.generate_content([video_file, prompt])
    return response.text


def transcribe_audio(media_path: str) -> str:
    """
    Transcribe speech from an audio or video file using Gemini.

    Used for: generating transcripts of Dean's voiceover recordings,
    saved to voice/transcripts/.

    Note: For word-level timestamps (needed for Shorts subtitles), use
    Whisper via generate_shorts.py instead — Gemini transcription does not
    reliably return per-word timing.

    Args:
        media_path: Path to the audio or video file.

    Returns:
        Plain text transcript as a string.

    TODO:
        - Upload file via genai.upload_file()
        - Prompt model to return a clean transcript, no timestamps
        - Return response.text
        - Handle long files by splitting if needed
    """
    model = _get_model(lite=False)
    audio_file = genai.upload_file(media_path)
    while audio_file.state.name == "PROCESSING":
        time.sleep(5)
        audio_file = genai.get_file(audio_file.name)
    response = model.generate_content([
        audio_file,
        "Transcribe this audio exactly as spoken. Return only the transcript text, no timestamps or labels."
    ])
    return response.text


def generate_text(prompt: str, lite: bool = False) -> str:
    """
    Send a plain text prompt to Gemini and return the response.

    Args:
        prompt: The full text prompt.
        lite:   If True, use gemini-2.5-flash-lite (faster, cheaper).
                Default False uses gemini-2.5-flash.

    Returns:
        The model's text response as a string.

    TODO:
        - Call model.generate_content(prompt)
        - Return response.text
        - Add retry logic for rate limit errors (exponential backoff)
    """
    try:
        model = _get_model(lite=lite)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"[gemini_client] generate_text error: {e}")
        raise


def detect_moments(video_path: str) -> list[dict]:
    """
    Analyse a finished long-form video and identify 3–6 moments suitable
    for YouTube Shorts.

    Criteria the model looks for:
      - Strong opinions or hot takes
      - Surprising or counterintuitive stats
      - Emotional peaks (frustration, excitement, disbelief)
      - Hooks that land within the first 3 seconds of the clip
      - Natural start/end points — no cut mid-sentence

    Each clip must be under 30 seconds.

    Args:
        video_path: Path to the finished long-form MP4.

    Returns:
        List of dicts, each with keys:
          {
            "start_seconds": int,
            "end_seconds": int,
            "reason": str   # why this moment works as a Short
          }

    TODO:
        - Upload video via analyze_video() helper
        - Build a structured JSON-requesting prompt
        - Parse response.text as JSON (handle markdown code blocks)
        - Validate each entry has required keys and end > start
        - Return parsed list
    """
    try:
        prompt = """
        Watch this hockey commentary video and identify 3 to 6 moments that
        would work as standalone YouTube Shorts (under 30 seconds each).

        Look specifically for:
        - Strong opinions or hot takes the host expresses
        - Surprising or counterintuitive stats
        - Emotional peaks — frustration, excitement, or disbelief
        - Moments where the hook lands within the first 3 seconds
        - Clean natural start and end points (no cut mid-sentence)

        Return ONLY a JSON array with no markdown wrapping. Format:
        [
          {
            "start_seconds": <integer>,
            "end_seconds": <integer>,
            "reason": "<one sentence explanation>"
          }
        ]
        """
        raw = analyze_video(video_path, prompt)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        moments = json.loads(raw)
        # Validate structure
        validated = []
        for m in moments:
            if "start_seconds" in m and "end_seconds" in m and m["end_seconds"] > m["start_seconds"]:
                validated.append(m)
        return validated
    except Exception as e:
        print(f"[gemini_client] detect_moments error: {e}")
        raise
