"""
assemble_video.py — Video Assembly Pipeline (with copyright-safe breaks + sound design)
========================================================================================

Step-by-step:
  1. Scan clips/approved/ for approved clip files (MP4) + their JSON sidecars
  2. Normalize every clip to 1920x1080 @ 30fps, silent (so concat is glitch-free)
  3. Between every pair of clips that has visual_break_after=True, insert a
     1.5s stat-board card built from the clip's metadata. This breaks up
     consecutive footage and prevents YouTube copyright matching from triggering
     on stacked highlights — the explicit rule from DEAN.md.
  4. Concatenate the (clip + break) sequence into a single silent b-roll track
  5. Locate Dean's voiceover in pipeline/recorded/ (most recent file)
  6. Lay the voiceover over the b-roll. Voiceover drives total duration.
  7. Mix a soft music bed under the voiceover (ducked, optional — needs an asset
     in config/sfx/), and a whoosh SFX cue at the start of every visual break
     (also optional — silently skipped if asset missing).
  8. Apply 0.5s fade-in / fade-out and export to outputs/long-form/

Run:
    python assemble_video.py
    python assemble_video.py --title "stenberg-replicated"
    python assemble_video.py --topic-type biography      # picks reflective music bed
    python assemble_video.py --no-music --no-sfx         # silence the layers
    python assemble_video.py --clips-only                # b-roll preview, no voiceover

Requires:
  - FFmpeg + ffprobe on PATH (or at /opt/homebrew/bin/)
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths and config
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

APPROVED_CLIPS_DIR    = _PROJECT_ROOT / "clips" / "approved"
RECORDED_DIR          = _PROJECT_ROOT / "pipeline" / "recorded"
LONG_FORM_OUTPUT_DIR  = _PROJECT_ROOT / "outputs" / "long-form"
SFX_DIR               = _PROJECT_ROOT / "config" / "sfx"

TODAY = datetime.date.today().isoformat()
CLIP_EXTENSIONS  = {".mp4", ".mov", ".mkv"}
AUDIO_EXTENSIONS = {".mp4", ".mov", ".m4a", ".wav", ".aac"}

# Output spec — fixed so concat works without re-encoding glitches
OUT_W, OUT_H, OUT_FPS = 1920, 1080, 30

# Visual break length (seconds). Long enough to read the headline, short enough
# to keep momentum.
BREAK_DURATION = 1.5

# Color palette for break cards (Canucks-leaning dark blue + accent)
BREAK_BG    = "0x0d2444"
BREAK_TEXT  = "white"
BREAK_SUB   = "0xCBA15A"

# Music bed level under voiceover (negative dB)
MUSIC_BED_DB = "-22dB"

# Music bed file (by topic_type). Falls back to first available if specified one missing.
MUSIC_BEDS = {
    "biography":  "bed_reflective.mp3",
    "incident":   "bed_intense.mp3",
    "general":    "bed_intense.mp3",
    "auto":       "bed_intense.mp3",
}

WHOOSH_SFX = "whoosh.wav"


# ---------------------------------------------------------------------------
# FFmpeg discovery
# ---------------------------------------------------------------------------

def _find_binary(name: str) -> str:
    """Return path to an ffmpeg/ffprobe binary, checking PATH then common Homebrew locations."""
    found = shutil.which(name)
    if found:
        return found
    for cand in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(cand):
            return cand
    raise EnvironmentError(
        f"{name} not found. Install with: brew install ffmpeg "
        "(see SETUP.md for non-technical instructions)."
    )

FFMPEG  = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_approved_clips() -> list[Path]:
    """Sorted list of approved clips. Errors if empty."""
    clips = sorted(
        f for f in APPROVED_CLIPS_DIR.iterdir() if f.suffix.lower() in CLIP_EXTENSIONS
    )
    if not clips:
        raise ValueError(
            f"No clips found in {APPROVED_CLIPS_DIR}. "
            "Move approved clips there before running assembly."
        )
    return clips


def find_voiceover() -> Path:
    """Most recently modified media file in pipeline/recorded/."""
    files = sorted(
        (f for f in RECORDED_DIR.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"No voiceover file found in {RECORDED_DIR}. "
            "Drop your recording there before running assembly."
        )
    print(f"[assemble_video] Using voiceover: {files[0].name}")
    return files[0]


def load_clip_metadata(clip_path: Path) -> dict:
    """Load the JSON sidecar next to a clip. Returns {} if missing."""
    json_path = clip_path.with_suffix(".json")
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def get_duration(path: Path) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Visual break cards (the copyright fix)
# ---------------------------------------------------------------------------

# System font candidates (Pillow tries these in order)
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load the first available system font at the given size."""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default(size)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Parse '0x0d2444' or '#0d2444' or 'white' to RGB tuple."""
    named = {"white": (255, 255, 255), "black": (0, 0, 0)}
    if h in named:
        return named[h]
    s = h.lstrip("#").removeprefix("0x")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def _break_card_text(metadata: dict, index: int) -> tuple[str, str]:
    """
    Pick a headline + subtitle pair to render on the break card from clip metadata.
    Tries (in priority order): section, topic, video_title.
    """
    section = (metadata.get("section") or "").strip()
    topic   = (metadata.get("topic") or "").strip()
    title   = (metadata.get("video_title") or "").strip()
    channel = (metadata.get("channel_name") or "").strip()

    # Headline: prefer a short section label if present, else the topic, else "Highlight N+1"
    if section:
        headline = section
    elif topic:
        headline = topic.split("|")[0].split(" - ")[0].strip()
    elif title:
        headline = title.split("|")[0].split(" - ")[0].strip()
    else:
        headline = f"Highlight {index + 1}"
    headline = headline[:42]

    # Subtitle: prefer the source title (truncated), else the channel
    if title and title != headline:
        subtitle = title.split("|")[0].split(" - ")[0].strip()[:60]
    elif channel:
        subtitle = f"via {channel}"
    elif topic:
        subtitle = topic[:60]
    else:
        subtitle = ""

    return headline, subtitle


def _render_card_png(headline: str, subtitle: str, png_path: Path) -> Path:
    """Render the break card as a PNG using Pillow (avoids ffmpeg drawtext dependency)."""
    bg = _hex_to_rgb(BREAK_BG)
    text_color = _hex_to_rgb(BREAK_TEXT)
    sub_color = _hex_to_rgb(BREAK_SUB)

    img = Image.new("RGB", (OUT_W, OUT_H), bg)
    draw = ImageDraw.Draw(img)

    # Word-wrap the headline if it's too long for one line
    headline_font = _load_font(110)
    sub_font = _load_font(44)

    def text_size(t: str, f) -> tuple[int, int]:
        bbox = draw.textbbox((0, 0), t, font=f)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Shrink headline font if it overflows
    while headline:
        w, _ = text_size(headline, headline_font)
        if w <= OUT_W - 120:
            break
        size = headline_font.size - 6
        if size < 60:
            # Hard truncate
            while headline and text_size(headline + "…", headline_font)[0] > OUT_W - 120:
                headline = headline[:-1]
            headline = (headline.rstrip() + "…") if headline else "…"
            break
        headline_font = _load_font(size)

    h_w, h_h = text_size(headline, headline_font)

    if subtitle:
        s_w, s_h = text_size(subtitle, sub_font)
    else:
        s_w = s_h = 0

    # Center both lines vertically as a block
    block_h = h_h + (40 + s_h if subtitle else 0)
    y0 = (OUT_H - block_h) // 2

    # Headline with stroke
    headline_x = (OUT_W - h_w) // 2
    draw.text(
        (headline_x, y0),
        headline,
        font=headline_font,
        fill=text_color,
        stroke_width=4,
        stroke_fill=(0, 0, 0),
    )

    if subtitle:
        sub_x = (OUT_W - s_w) // 2
        sub_y = y0 + h_h + 40
        draw.text(
            (sub_x, sub_y),
            subtitle,
            font=sub_font,
            fill=sub_color,
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

    img.save(png_path, "PNG")
    return png_path


def make_break_card(metadata: dict, output_path: Path, index: int) -> Path:
    """
    Render a 1.5s break card as a 1920x1080@30 silent MP4.
    Headline + subtitle laid out via Pillow on a solid color background.
    """
    headline, subtitle = _break_card_text(metadata, index)
    png_path = output_path.with_suffix(".png")
    _render_card_png(headline, subtitle, png_path)

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-t", str(BREAK_DURATION), "-i", str(png_path),
        "-r", str(OUT_FPS),
        "-vf", f"scale={OUT_W}:{OUT_H},setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Break card render failed:\n{result.stderr}")
    return output_path


# ---------------------------------------------------------------------------
# Clip normalization (so concat is seamless)
# ---------------------------------------------------------------------------

def normalize_clip(src: Path, dst: Path) -> Path:
    """
    Re-encode a clip to the canonical output spec: 1920x1080 @ 30fps, silent,
    H.264 + yuv420p. This guarantees the concat demuxer joins them cleanly.

    Letterbox/pillarbox to preserve original aspect ratio.
    """
    vf = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={OUT_FPS}"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        "-r", str(OUT_FPS),
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Clip normalization failed for {src.name}:\n{result.stderr}")
    return dst


# ---------------------------------------------------------------------------
# Build the b-roll track (clips + visual breaks)
# ---------------------------------------------------------------------------

def build_broll_track(clip_paths: list[Path], work_dir: Path) -> tuple[Path, list[float]]:
    """
    Normalize clips, generate visual break cards between flagged clips, concat
    them in order. Returns:
      (path_to_silent_broll_mp4, list_of_break_start_times_in_seconds)
    The break times are useful for placing a whoosh SFX cue at each break.
    """
    print(f"[assemble_video] Building b-roll track from {len(clip_paths)} clips...")
    work_dir.mkdir(parents=True, exist_ok=True)

    segments: list[Path] = []
    break_times: list[float] = []
    cumulative_time = 0.0

    for i, clip in enumerate(clip_paths):
        meta = load_clip_metadata(clip)
        norm = normalize_clip(clip, work_dir / f"clip-{i:02d}.mp4")
        segments.append(norm)
        cumulative_time += get_duration(norm)
        print(f"  + clip {i+1}: {clip.name} ({get_duration(norm):.1f}s)")

        is_last = (i == len(clip_paths) - 1)
        if meta.get("visual_break_after", False) and not is_last:
            break_path = make_break_card(meta, work_dir / f"break-{i:02d}.mp4", i)
            segments.append(break_path)
            break_times.append(cumulative_time)
            cumulative_time += BREAK_DURATION
            print(f"    → break: \"{_break_card_text(meta, i)[0]}\"")

    # Concat list
    concat_list = work_dir / "concat.txt"
    with concat_list.open("w") as f:
        for s in segments:
            f.write(f"file '{s.resolve()}'\n")

    out = work_dir / "broll.mp4"
    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{result.stderr}")

    print(f"[assemble_video] B-roll built: {get_duration(out):.1f}s, {len(break_times)} break cards inserted")
    return out, break_times


# ---------------------------------------------------------------------------
# Sound design — music bed + SFX cues
# ---------------------------------------------------------------------------

def _resolve_music_bed(topic_type: str) -> Path | None:
    """Find the music bed for this topic_type, or any available bed as fallback."""
    if not SFX_DIR.exists():
        return None
    preferred = SFX_DIR / MUSIC_BEDS.get(topic_type, MUSIC_BEDS["auto"])
    if preferred.exists():
        return preferred
    # Fallback: any bed_*.mp3 / .wav
    for cand in SFX_DIR.glob("bed_*"):
        if cand.suffix.lower() in {".mp3", ".wav", ".aac", ".m4a"}:
            return cand
    return None


def _resolve_whoosh() -> Path | None:
    """Find the whoosh SFX file, or any *_sfx.wav fallback."""
    if not SFX_DIR.exists():
        return None
    preferred = SFX_DIR / WHOOSH_SFX
    if preferred.exists():
        return preferred
    for cand in SFX_DIR.glob("*"):
        if cand.suffix.lower() in {".wav", ".mp3"} and "whoosh" in cand.stem.lower():
            return cand
    return None


def lay_voiceover_with_sound_design(
    broll_path: Path,
    voiceover_path: Path,
    break_times: list[float],
    topic_type: str,
    work_dir: Path,
    use_music: bool = True,
    use_sfx: bool = True,
) -> Path:
    """
    Lay voiceover + (optional) music bed + (optional) whoosh SFX over the b-roll.
    Voiceover is the loudest layer and drives total duration.

    Music bed: continuous, ducked to MUSIC_BED_DB (~-22dB) under voiceover.
    SFX: a whoosh placed at each break-card start time.

    All layers gracefully degrade if assets are missing — script never errors out
    on a missing SFX file.
    """
    vo_duration = get_duration(voiceover_path)
    broll_duration = get_duration(broll_path)
    print(f"[assemble_video] Voiceover: {vo_duration:.1f}s | B-roll: {broll_duration:.1f}s")

    # Loop b-roll to cover voiceover duration
    loops = max(1, int(vo_duration / max(broll_duration, 0.01)) + 1)

    music_bed = _resolve_music_bed(topic_type) if use_music else None
    whoosh    = _resolve_whoosh() if use_sfx else None

    inputs = [
        ["-stream_loop", str(loops), "-i", str(broll_path)],   # 0: video (looped)
        ["-i", str(voiceover_path)],                            # 1: voiceover
    ]
    next_idx = 2
    music_idx = None
    whoosh_idx = None

    if music_bed is not None:
        inputs.append(["-stream_loop", "-1", "-i", str(music_bed)])
        music_idx = next_idx
        next_idx += 1
    else:
        if use_music:
            print(f"[assemble_video] Note: no music bed found in {SFX_DIR} — skipping music layer")

    if whoosh is not None and break_times:
        inputs.append(["-i", str(whoosh)])
        whoosh_idx = next_idx
        next_idx += 1
    elif use_sfx:
        if not whoosh:
            print(f"[assemble_video] Note: no whoosh SFX found in {SFX_DIR} — skipping SFX layer")
        elif not break_times:
            print(f"[assemble_video] Note: no break cards in this cut — no SFX to place")

    # Build the audio filter graph
    audio_chunks = []
    audio_label_inputs = ["[1:a]"]  # voiceover always present

    if music_idx is not None:
        # Trim music to vo_duration, set volume
        audio_chunks.append(
            f"[{music_idx}:a]aformat=channel_layouts=stereo,"
            f"atrim=0:{vo_duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume={MUSIC_BED_DB}[music]"
        )
        audio_label_inputs.append("[music]")

    if whoosh_idx is not None:
        # For each break time, place a whoosh with adelay
        whoosh_labels = []
        for i, t in enumerate(break_times):
            delay_ms = max(0, int(t * 1000) - 100)  # slight pre-roll
            audio_chunks.append(
                f"[{whoosh_idx}:a]aformat=channel_layouts=stereo,"
                f"adelay={delay_ms}|{delay_ms},"
                f"atrim=0:{vo_duration:.3f},"
                f"volume=-3dB[w{i}]"
            )
            whoosh_labels.append(f"[w{i}]")
        audio_label_inputs.extend(whoosh_labels)

    # Mix everything
    n_audio_inputs = len(audio_label_inputs)
    if n_audio_inputs == 1:
        # Just voiceover — keep it simple
        mix_step = ""
        final_audio_label = "[1:a]"
    else:
        mix_step = (
            "".join(audio_label_inputs)
            + f"amix=inputs={n_audio_inputs}:duration=first:dropout_transition=0:normalize=0"
            + f",afade=t=in:st=0:d=0.5,afade=t=out:st={vo_duration - 0.5:.3f}:d=0.5[mixed]"
        )
        final_audio_label = "[mixed]"

    filter_parts = list(audio_chunks)
    if mix_step:
        filter_parts.append(mix_step)

    # Video: trim looped b-roll to vo_duration + apply fades
    video_step = (
        f"[0:v]trim=0:{vo_duration:.3f},setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={vo_duration - 0.5:.3f}:d=0.5[v]"
    )
    filter_parts.insert(0, video_step)

    filter_complex = ";".join(filter_parts)

    out = work_dir / "final.mp4"
    cmd = [FFMPEG, "-y"]
    for grp in inputs:
        cmd.extend(grp)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", final_audio_label,
        "-t", f"{vo_duration:.3f}",
        "-c:v", "libx264", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(OUT_FPS),
        "-pix_fmt", "yuv420p",
        str(out),
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Print the filter graph for debug, then re-raise
        print("[assemble_video] filter_complex was:\n  " + filter_complex)
        raise RuntimeError(f"Final mix failed:\n{result.stderr[-1500:]}")
    return out


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_video(assembled_path: Path, title: str) -> Path:
    LONG_FORM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace(" ", "-").lower()[:60] or "video"
    output_path = LONG_FORM_OUTPUT_DIR / f"{TODAY}-{safe_title}.mp4"
    shutil.move(str(assembled_path), str(output_path))
    print(f"[assemble_video] Exported to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Assemble approved clips + voiceover into a finished video with "
                    "copyright-safe visual breaks and sound design."
    )
    parser.add_argument("--title", default="video",
                        help="Output filename suffix (default: 'video')")
    parser.add_argument("--topic-type", default="auto",
                        choices=["biography", "incident", "general", "auto"],
                        help="Drives music bed selection")
    parser.add_argument("--clips-only", action="store_true",
                        help="Build the b-roll track only (no voiceover, no music, no SFX)")
    parser.add_argument("--no-music", action="store_true", help="Skip music bed")
    parser.add_argument("--no-sfx", action="store_true", help="Skip whoosh SFX cues")
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="deaner-assemble-"))

    try:
        clip_paths = find_approved_clips()
        broll_path, break_times = build_broll_track(clip_paths, work_dir)

        if args.clips_only:
            output_path = export_video(broll_path, args.title)
            print(f"[assemble_video] Done (clips only). {output_path}")
            return

        voiceover_path = find_voiceover()
        final_path = lay_voiceover_with_sound_design(
            broll_path,
            voiceover_path,
            break_times,
            args.topic_type,
            work_dir,
            use_music=not args.no_music,
            use_sfx=not args.no_sfx,
        )
        output_path = export_video(final_path, args.title)
        print(f"[assemble_video] Done. {output_path}")

    except (ValueError, FileNotFoundError) as e:
        print(f"[assemble_video] Setup error: {e}")
    except subprocess.CalledProcessError as e:
        print(f"[assemble_video] FFmpeg error: {e.stderr}")
        raise
    finally:
        # Clean up the temp working dir
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
