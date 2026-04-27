"""
assemble_video.py — Video Assembly Pipeline
============================================

Step-by-step:
  1. Scan clips/approved/ for approved clip files (MP4) + their JSON sidecars
  2. Reorder clips so no two consecutive clips share the same source video URL
     (copyright safety — same-source clips placed apart, not back-to-back)
  3. Normalize every clip to 1920x1080 @ 30fps, silent, H.264/yuv420p
  4. Concatenate with hard cuts into a silent b-roll track; optional project
     timeline overlays official score/boxscore screenshots over active video
  5. Locate Dean's voiceover in pipeline/recorded/ (most recent file)
  6. Refuse assembly if b-roll is shorter than voiceover; never loop footage
  7. Lay VO on top and export to outputs/long-form/

Run:
    python assemble_video.py
    python assemble_video.py --title "stenberg"
    python assemble_video.py --clips-only    # b-roll preview, no voiceover
    python assemble_video.py --edit-mode hard-cuts --no-music

Requires:
  - FFmpeg + ffprobe on PATH (or at /opt/homebrew/bin/)
"""

import argparse
import datetime
import json
import math
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from dotenv import load_dotenv
from utils.projects import resolve_project, write_default_requirements

# ---------------------------------------------------------------------------
# Paths and config
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

APPROVED_CLIPS_DIR   = _PROJECT_ROOT / "clips" / "approved"
RECORDED_DIR         = _PROJECT_ROOT / "pipeline" / "recorded"
LONG_FORM_OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "long-form"
SFX_DIR              = _PROJECT_ROOT / "config" / "sfx"

TODAY = datetime.date.today().isoformat()
CLIP_EXTENSIONS  = {".mp4", ".mov", ".mkv"}
AUDIO_EXTENSIONS = {".mp4", ".mov", ".m4a", ".wav", ".aac"}
REJECTED_CHANNELS = {
    "center ice central",
    "creepthejeep",
    "jonathan hawkey",
    "hawkey productions",
    "next man up",
    "eck",
    "nuckhead",
    "habscentral",
    "hockey trend",
}
REJECTED_TITLE_KEYWORDS = {
    "full clip coming",
    "full clip",
    "subscribe",
    "subscribed",
    "like and subscribe",
    "smash that like",
    "turn on notifications",
    "creep the jeep",
    "creepthejeep",
    "center ice central",
    "lineups",
    "how do i get out",
    "all star game",
}
REJECTED_VISUAL_KEYWORDS = {
    "xbox",
    "ea sports",
    "nhl 24",
    "nhl 25",
    "nhl 26",
    "gameplay",
    "franchise mode",
    "simulation",
    "podcast",
    "watchalong",
    "fans react",
}

# Output spec — fixed so concat is glitch-free
OUT_W, OUT_H, OUT_FPS = 1920, 1080, 30

# Clip duration limits (seconds)
MIN_CLIP_DURATION = 3.0
MAX_CLIP_DURATION = 4.9
MAX_GRAPHIC_DURATION = 10.0
CARD_DURATION = 8.0
CARD_EVERY_N_CLIPS = 7
MUSIC_BED = SFX_DIR / "bed_intense.mp3"
MUSIC_VOLUME = 0.12
CROP_ZOOM = 1.08


def pick_music_bed(title: str = "") -> Path | None:
    beds = sorted(SFX_DIR.glob("bed_*.mp3"))
    if not beds:
        return None
    seed = title or datetime.date.today().isoformat()
    return beds[sum(ord(ch) for ch in seed) % len(beds)]


# ---------------------------------------------------------------------------
# FFmpeg discovery
# ---------------------------------------------------------------------------

def _find_binary(name: str) -> str:
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

def find_approved_clips(approved_dir: Path = APPROVED_CLIPS_DIR) -> list[Path]:
    clips = sorted(
        f for f in approved_dir.iterdir() if f.suffix.lower() in CLIP_EXTENSIONS
    ) if approved_dir.exists() else []
    if not clips:
        raise ValueError(
            f"No clips found in {approved_dir}. "
            "Move approved clips there before running assembly."
        )
    return clips


def find_voiceover(recorded_dir: Path = RECORDED_DIR) -> Path:
    files = sorted(
        (f for f in recorded_dir.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS) if recorded_dir.exists() else [],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"No voiceover file found in {recorded_dir}. "
            "Drop your recording there before running assembly."
        )
    print(f"[assemble_video] Using voiceover: {files[0].name}")
    return files[0]


def load_clip_metadata(clip_path: Path) -> dict:
    json_path = clip_path.with_suffix(".json")
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _clip_reject_reasons(clip_path: Path) -> list[str]:
    meta = load_clip_metadata(clip_path)
    channel = (meta.get("channel_name") or "").strip().lower()
    title = (meta.get("video_title") or "").strip().lower()
    text = f"{channel} {title}"
    reasons = []

    if channel in REJECTED_CHANNELS:
        reasons.append(f"known bad channel: {meta.get('channel_name')}")
    for keyword in sorted(REJECTED_TITLE_KEYWORDS):
        if keyword in text:
            reasons.append(f"title/source keyword: {keyword}")
            break
    for keyword in sorted(REJECTED_VISUAL_KEYWORDS):
        if keyword in text:
            reasons.append(f"rejected visual keyword: {keyword}")
            break
    return reasons


def _detect_black_segments(path: Path, min_duration: float = 0.45) -> list[str]:
    result = subprocess.run(
        [
            FFMPEG, "-hide_banner", "-i", str(path),
            "-vf", f"blackdetect=d={min_duration:.2f}:pix_th=0.10",
            "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    segments = []
    for line in result.stderr.splitlines():
        if "black_start:" in line and "black_duration:" in line:
            segments.append(line.split("]", 1)[-1].strip())
    return segments


def audit_approved_clips(clip_paths: list[Path], project=None) -> None:
    """Fail fast when approved clips contain obvious title cards or black screens."""
    issues: list[str] = []
    for clip in clip_paths:
        reasons = _clip_reject_reasons(clip)
        for reason in reasons:
            issues.append(f"- `{clip.name}` — {reason}")
        black_segments = _detect_black_segments(clip)
        for segment in black_segments:
            issues.append(f"- `{clip.name}` — black-screen segment detected ({segment})")

    if not issues:
        return

    report = (
        "# Clip Audit: Needs Review\n\n"
        "Assembly stopped because approved clips include visuals that violate "
        "Dean's demo requirements.\n\n"
        + "\n".join(issues)
        + "\n"
    )
    if project:
        audit_path = project.notes_dir / f"{project.package_slug}-clip-audit.md"
        audit_path.write_text(report, encoding="utf-8")
        print(f"[assemble_video] Clip audit failed: {audit_path}")
    else:
        print(report)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def get_duration(path: Path) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _ffmpeg_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("%", "\\%")
    )


def _card_text_for_cluster(cluster: list[Path], index: int) -> tuple[str, str]:
    topics = []
    channels = []
    for clip in cluster:
        meta = load_clip_metadata(clip)
        title = (meta.get("video_title") or "").split("|")[0].strip()
        channel = (meta.get("channel_name") or "").strip()
        if title:
            topics.append(title)
        if channel and channel not in channels:
            channels.append(channel)
    headline_options = [
        "THE TARGET KEEPS GETTING BIGGER",
        "EVERYONE WANTED A PIECE",
        "OLD-SCHOOL HOCKEY IS BACK",
        "THE LEAGUE HAD TO NOTICE",
        "THIS IS WHY IT BLEW UP",
    ]
    headline = headline_options[index % len(headline_options)]
    subtitle = ", ".join(channels[:3]) if channels else (topics[0][:70] if topics else "Context break")
    return headline, subtitle


def render_context_card(headline: str, subtitle: str, dst: Path, duration: float = CARD_DURATION) -> Path:
    """Legacy helper kept for compatibility; current assembly does not call it."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        raise RuntimeError(f"Pillow is required for legacy image segments: {e}")

    wrapped_headline = "\n".join(textwrap.wrap(headline.upper(), width=24)[:2])
    wrapped_subtitle = "\n".join(textwrap.wrap(subtitle, width=58)[:2])

    img = Image.new("RGB", (OUT_W, OUT_H), (6, 21, 34))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((80, 86, 1840, 994), radius=0, fill=(11, 35, 56))
    draw.rectangle((80, 86, 1840, 100), fill=(255, 210, 0))

    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    def load_font(size: int):
        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    headline_font = load_font(86)
    subtitle_font = load_font(38)

    def draw_centered_multiline(text: str, font, y: int, fill):
        lines = text.split("\n")
        line_heights = []
        widths = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            widths.append(bbox[2] - bbox[0])
            line_heights.append(bbox[3] - bbox[1])
        total_h = sum(line_heights) + max(0, len(lines) - 1) * 18
        cur_y = y - total_h // 2
        for line, width, height in zip(lines, widths, line_heights):
            draw.text(((OUT_W - width) // 2, cur_y), line, font=font, fill=fill)
            cur_y += height + 18

    draw_centered_multiline(wrapped_headline, headline_font, 430, (255, 255, 255))
    draw_centered_multiline(wrapped_subtitle, subtitle_font, 640, (255, 210, 0))

    png_path = dst.with_suffix(".png")
    img.save(png_path)

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", str(png_path),
        "-t", f"{duration:.1f}",
        "-r", str(OUT_FPS),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Context card render failed:\n{result.stderr[-1500:]}")
    return dst


def _max_duration_for_clip(path: Path) -> float:
    meta = load_clip_metadata(path)
    content_type = (meta.get("content_type") or "").lower()
    if content_type in {"graphic", "scorecard", "stat_card", "ranking", "screenshot"}:
        return MAX_GRAPHIC_DURATION
    return MAX_CLIP_DURATION


def usable_clip_duration(path: Path) -> float:
    """Duration contribution after normalization rules are applied."""
    raw_dur = get_duration(path)
    if raw_dur < MIN_CLIP_DURATION:
        return 0.0
    return min(raw_dur, _max_duration_for_clip(path))


def preflight_clip_duration(clip_paths: list[Path], edit_mode: str = "retention") -> tuple[float, int]:
    usable_durations = [usable_clip_duration(path) for path in clip_paths]
    usable_count = sum(1 for dur in usable_durations if dur > 0)
    total = sum(usable_durations)
    return total, usable_count


def clip_source_key(clip: Path) -> str:
    meta = load_clip_metadata(clip)
    return meta.get("source_url") or meta.get("video_title") or clip.stem


# ---------------------------------------------------------------------------
# Source diversity — no consecutive clips from the same video
# ---------------------------------------------------------------------------

def reorder_for_diversity(clip_paths: list[Path]) -> list[Path]:
    """
    Reorder clips so no two consecutive clips share the same source_url.
    Uses a round-robin across source groups. Falls back to original order
    if all clips are from the same source (rare but handled).
    """
    # Group by source_url
    groups: dict[str, list[Path]] = {}
    for clip in clip_paths:
        groups.setdefault(clip_source_key(clip), []).append(clip)

    if len(groups) == 1:
        # All from same source — warn but proceed (gather_clips should have prevented this)
        print("[assemble_video] WARNING: all clips are from the same source video. "
              "Re-gather clips from multiple sources for copyright safety.")
        return clip_paths

    # Round-robin across groups
    ordered: list[Path] = []
    buckets = list(groups.values())
    i = 0
    while any(buckets):
        bucket = buckets[i % len(buckets)]
        if bucket:
            ordered.append(bucket.pop(0))
        i += 1

    for prev, cur in zip(ordered, ordered[1:]):
        if clip_source_key(prev) == clip_source_key(cur):
            print("[assemble_video] WARNING: adjacent clips share a source video after "
                  "diversity ordering. Re-gather more source videos for best results.")
            break

    return ordered


# ---------------------------------------------------------------------------
# Clip normalization
# ---------------------------------------------------------------------------

def normalize_clip(src: Path, dst: Path) -> Path | None:
    """
    Re-encode clip to 1920x1080 @ 30fps, silent, H.264/yuv420p.
    Enforces MIN/MAX clip duration by trimming if needed.
    """
    raw_dur = get_duration(src)
    if raw_dur < MIN_CLIP_DURATION:
        print(f"[assemble_video] WARNING: skipping {src.name} "
              f"({raw_dur:.2f}s, shorter than {MIN_CLIP_DURATION:.1f}s)")
        return None
    trim_dur = min(raw_dur, _max_duration_for_clip(src))

    zoom_w = int(OUT_W * CROP_ZOOM)
    zoom_h = int(OUT_H * CROP_ZOOM)
    vf = (
        f"scale={zoom_w}:{zoom_h}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},setsar=1,fps={OUT_FPS}"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", str(src),
        "-t", f"{trim_dur:.1f}",
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
# Build the b-roll track — hard cuts only
# ---------------------------------------------------------------------------

def build_broll_track(clip_paths: list[Path], work_dir: Path, edit_mode: str = "retention") -> Path:
    """
    Normalize clips, enforce source diversity, concatenate with hard cuts.
    Returns path to the silent b-roll MP4.
    """
    print(f"[assemble_video] Building b-roll track from {len(clip_paths)} clips ({edit_mode})...")
    work_dir.mkdir(parents=True, exist_ok=True)

    ordered = reorder_for_diversity(clip_paths)

    segments: list[Path] = []
    for i, clip in enumerate(ordered):
        norm = normalize_clip(clip, work_dir / f"clip-{i:02d}.mp4")
        if norm is None:
            continue
        dur = get_duration(norm)
        meta = load_clip_metadata(clip)
        src_label = (meta.get("channel_name") or meta.get("source_url") or "?")[:40]
        print(f"  + clip {i+1}: {clip.name} ({dur:.1f}s) — {src_label}")
        segments.append(norm)

    if not segments:
        raise RuntimeError("No usable clips remain after normalization.")

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

    total_dur = get_duration(out)
    print(f"[assemble_video] B-roll built: {total_dur:.1f}s, {len(segments)} segment(s)")
    return out


def _overlay_position_expr(position: str) -> tuple[str, str]:
    position = (position or "top_right").lower().replace("-", "_")
    margin = "56"
    positions = {
        "top_right": (f"W-w-{margin}", margin),
        "top_left": (margin, margin),
        "bottom_right": (f"W-w-{margin}", f"H-h-{margin}"),
        "bottom_left": (margin, f"H-h-{margin}"),
        "center": ("(W-w)/2", "(H-h)/2"),
        "center_upper": ("(W-w)/2", "H*0.16"),
        "upper_center": ("(W-w)/2", "H*0.16"),
        "middle": ("(W-w)/2", "(H-h)/2"),
    }
    return positions.get(position, positions["top_right"])


def apply_visual_overlays(broll_path: Path, project, work_dir: Path) -> Path:
    """
    Overlay official score/boxscore screenshots from timeline/visual-plan.json.

    Entries:
      {"overlay_image": "assets/scorecards/file.png", "start": 42,
       "duration": 7, "position": "top_right", "scale": 0.42}
    """
    if not project:
        return broll_path

    plan_path = project.root / "timeline" / "visual-plan.json"
    if not plan_path.exists():
        return broll_path

    try:
        entries = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[assemble_video] WARNING: could not read visual plan: {e}")
        return broll_path

    if isinstance(entries, dict):
        entries = entries.get("overlays", [])
    entries = [entry for entry in entries if entry.get("overlay_image")]
    if not entries:
        return broll_path

    cmd = [FFMPEG, "-y", "-i", str(broll_path)]
    valid_entries = []
    for entry in entries:
        overlay_path = Path(entry["overlay_image"])
        if not overlay_path.is_absolute():
            overlay_path = project.root / overlay_path
        if not overlay_path.exists():
            print(f"[assemble_video] WARNING: missing overlay image: {overlay_path}")
            continue
        valid_entries.append({**entry, "overlay_path": overlay_path})
        cmd.extend(["-i", str(overlay_path)])

    if not valid_entries:
        return broll_path

    filters = []
    current = "[0:v]"
    for idx, entry in enumerate(valid_entries, start=1):
        start = float(entry.get("start", 0))
        duration = max(0.5, float(entry.get("duration", 7)))
        end = start + duration
        scale = float(entry.get("scale", 0.76))
        scale = max(0.15, min(scale, 0.9))
        overlay_width = max(240, int(OUT_W * scale))
        x_expr, y_expr = _overlay_position_expr(entry.get("position", "top_right"))
        scaled = f"[ov{idx}]"
        out_label = f"[v{idx}]"
        filters.append(
            f"[{idx}:v]scale={overlay_width}:-1,format=rgba,colorchannelmixer=aa=0.96{scaled}"
        )
        filters.append(
            f"{current}{scaled}overlay=x={x_expr}:y={y_expr}:"
            f"enable='between(t,{start:.3f},{end:.3f})'{out_label}"
        )
        current = out_label

    out = work_dir / "broll-overlays.mp4"
    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", current,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        str(out),
    ])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[assemble_video] WARNING: overlay render failed:\n{result.stderr[-1500:]}")
        return broll_path
    print(f"[assemble_video] Applied {len(valid_entries)} screenshot overlay(s).")
    return out


# ---------------------------------------------------------------------------
# Lay voiceover over b-roll
# ---------------------------------------------------------------------------

def refuse_if_insufficient_clips(clip_paths: list[Path], voiceover_path: Path, title: str, edit_mode: str = "retention") -> None:
    vo_duration = get_duration(voiceover_path)
    clip_duration, usable_count = preflight_clip_duration(clip_paths, edit_mode=edit_mode)
    if clip_duration >= vo_duration:
        return

    missing = max(0.0, vo_duration - clip_duration)
    avg_clip = clip_duration / usable_count if usable_count else MAX_CLIP_DURATION
    more_needed = math.ceil(missing / max(avg_clip, 0.01))
    print("[assemble_video] ERROR: Not enough clips to fill the voiceover.")
    print(f"  Voiceover:  {vo_duration:.0f}s")
    print(f"  Clips:      {clip_duration:.0f}s ({usable_count} clips × ~{avg_clip:.1f}s)")
    print(f"  Missing:    {missing:.0f}s — gather ~{more_needed} more clips before assembling.")
    print(f'Run: python scripts/gather_clips.py --topic "{title}" --auto')
    raise SystemExit(1)


def lay_voiceover(broll_path: Path, voiceover_path: Path, work_dir: Path, music_path: Path | None = MUSIC_BED) -> Path:
    """
    Lay VO on top of the b-roll. Voiceover drives duration; b-roll is never looped.
    """
    vo_duration = get_duration(voiceover_path)
    broll_duration = get_duration(broll_path)
    print(f"[assemble_video] Voiceover: {vo_duration:.1f}s | B-roll: {broll_duration:.1f}s")

    if broll_duration < vo_duration:
        missing = vo_duration - broll_duration
        more_needed = math.ceil(missing / MAX_CLIP_DURATION)
        print("[assemble_video] ERROR: Not enough clips to fill the voiceover.")
        print(f"  Voiceover:  {vo_duration:.0f}s")
        print(f"  Clips:      {broll_duration:.0f}s")
        print(f"  Missing:    {missing:.0f}s — gather ~{more_needed} more clips before assembling.")
        raise SystemExit(1)

    out = work_dir / "final.mp4"
    cmd = [
        FFMPEG, "-y",
        "-i", str(broll_path),
        "-i", str(voiceover_path),
    ]
    if music_path and music_path.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(music_path)])

    if music_path and music_path.exists():
        cmd.extend([
            "-filter_complex",
            f"[2:a]volume={MUSIC_VOLUME}[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v:0",
            "-map", "[a]",
        ])
    else:
        cmd.extend([
            "-map", "0:v:0",
            "-map", "1:a:0",
        ])

    cmd.extend([
        "-t", f"{vo_duration:.3f}",
        "-c:v", "libx264", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(OUT_FPS),
        "-pix_fmt", "yuv420p",
        str(out),
    ])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Final mix failed:\n{result.stderr[-1500:]}")
    return out


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_video(assembled_path: Path, title: str, project=None) -> Path:
    output_dir = project.exports_dir if project else LONG_FORM_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace(" ", "-").lower()[:60] or "video"
    output_path = project.final_video_path if project else output_dir / f"{TODAY}-{safe_title}.mp4"
    shutil.move(str(assembled_path), str(output_path))
    print(f"[assemble_video] Exported to {output_path}")
    return output_path


def write_quality_proof(output_path: Path, voiceover_path: Path | None, clip_paths: list[Path], music_path: Path | None, project=None) -> None:
    if not project:
        return
    write_default_requirements(project, output_path.stem)
    duration = get_duration(output_path)
    voiceover_duration = get_duration(voiceover_path) if voiceover_path else 0.0
    music_line = f"- Music bed: `{music_path.name}`\n" if music_path else "- Music bed: none\n"
    proof = (
        f"# Quality Proof: {project.slug}\n\n"
        f"- Final export: `{output_path.name}`\n"
        f"- Final duration: {duration:.1f}s\n"
        f"- Voiceover duration: {voiceover_duration:.1f}s\n"
        f"{music_line}"
    )
    proof += (
        f"- Approved clips used: {len(clip_paths)}\n"
        "- Clip audit: passed before assembly.\n"
        "- No b-roll looping: confirmed by assembly preflight and no video stream loop path.\n"
        "- No abrupt ending: final duration is driven by the voiceover duration.\n"
        "- Slide cards/internal labels: not generated by assembly.\n"
        "- Gameplay/podcast/subscribe overlays: blocked by clip audit keywords and requires final manual watch confirmation.\n"
        "- Adjacent same-source clips: diversity ordering applied before concat.\n"
        "- Edit style: minimal hard cuts with light music under narration.\n"
    )
    project.proof_path.write_text(proof, encoding="utf-8")
    print(f"[assemble_video] Proof note: {project.proof_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Assemble approved clips + voiceover into a finished long-form video."
    )
    parser.add_argument("--title", default="video",
                        help="Output filename suffix (default: 'video')")
    parser.add_argument("--clips-only", action="store_true",
                        help="Build the b-roll track only (no voiceover)")
    parser.add_argument("--edit-mode", choices=("retention", "hard-cuts"), default="hard-cuts",
                        help="Compatibility flag. Current assembly uses hard cuts plus optional screenshot overlays.")
    parser.add_argument("--no-music", action="store_true",
                        help="Disable the low background music bed")
    parser.add_argument("--project", type=str, default="",
                        help="Optional project slug/path. Uses project clips, voiceover, and exports folder.")
    args = parser.parse_args()
    project = resolve_project(args.project, seed=args.title, create=bool(args.project))
    if project:
        write_default_requirements(project, args.title)
        print(f"[assemble_video] Project: {project.root}")

    work_dir = Path(tempfile.mkdtemp(prefix="deaner-assemble-"))

    try:
        approved_dir = project.approved_clips_dir if project else APPROVED_CLIPS_DIR
        recorded_dir = project.voiceover_dir if project else RECORDED_DIR
        clip_paths = find_approved_clips(approved_dir)
        audit_approved_clips(clip_paths, project=project)
        voiceover_path = None
        if not args.clips_only:
            voiceover_path = find_voiceover(recorded_dir)
            refuse_if_insufficient_clips(clip_paths, voiceover_path, args.title, edit_mode=args.edit_mode)

        broll_path = build_broll_track(clip_paths, work_dir, edit_mode=args.edit_mode)
        broll_path = apply_visual_overlays(broll_path, project, work_dir)

        if args.clips_only:
            output_path = export_video(broll_path, args.title, project=project)
            write_quality_proof(output_path, None, clip_paths, None, project=project)
            print(f"[assemble_video] Done (clips only). {output_path}")
            return

        music_path = None if args.no_music else pick_music_bed(args.title)
        if music_path:
            print(f"[assemble_video] Music bed: {music_path.name}")
        final_path = lay_voiceover(broll_path, voiceover_path, work_dir, music_path=music_path)
        output_path = export_video(final_path, args.title, project=project)
        write_quality_proof(output_path, voiceover_path, clip_paths, music_path, project=project)
        print(f"[assemble_video] Done. {output_path}")

    except (ValueError, FileNotFoundError) as e:
        print(f"[assemble_video] Setup error: {e}")
    except RuntimeError as e:
        print(f"[assemble_video] Error: {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
