# Deaner-HD — YouTube Automation System

This folder contains everything needed to run your hockey commentary channel
on autopilot. You don't need to be technical to use it day to day.

---

## What This System Does

1. **Finds video ideas** — polls NHL news feeds, Reddit, and competitor channels
2. **Writes outlines** — generates a structured script outline in your voice
3. **Gathers clips** — downloads relevant highlight footage automatically
4. **Assembles videos** — lays your voiceover over clips and exports a finished file
5. **Cuts Shorts** — finds the best moments in your long-form video and turns them into 9:16 Shorts with subtitles
6. **Writes metadata** — generates titles, descriptions, and tags ready to paste into YouTube

---

## Folder Guide

| Folder | What it's for |
|--------|---------------|
| `pipeline/ideas/` | AI-generated topic suggestions land here as dated markdown files |
| `pipeline/scripted/` | Approved outlines ready for you to record |
| `pipeline/recorded/` | Drop your raw voiceover files here after recording |
| `pipeline/editing/` | Work-in-progress edits live here temporarily |
| `pipeline/published/` | Move a project here once it's live on YouTube |
| `voice/scripts/` | Finished scripts you can re-use as style examples |
| `voice/transcripts/` | Auto-generated transcripts of your recordings |
| `clips/raw/` | Downloaded highlight clips before approval |
| `clips/approved/` | Clips you've okayed for use in the video |
| `outputs/long-form/` | Finished full-length videos ready to upload |
| `outputs/shorts/` | Finished Shorts (9:16) ready to upload |
| `config/` | Settings — feed sources, clip sources, API keys |
| `references/` | Your voice guide, signature phrases, and banned topics |
| `scripts/` | The automation code (you don't need to touch this) |

---

## Day-to-Day Workflow

### Step 1 — Get ideas
```
cd scripts
python fetch_ideas.py
```
Ideas land in `pipeline/ideas/` as a dated markdown file. Pick the topic you want to make.

### Step 2 — Gather clips
```
python gather_clips.py --topic "Your chosen topic"
```
Clips download to `clips/raw/` with a metadata JSON file alongside each one.

### Step 3 — Approve clips
Open `clips/raw/` and move the clips you want to use into `clips/approved/`.
Move the metadata JSON files over too — they travel with the clip.

### Step 4 — Generate the outline
```
python generate_outline.py --topic "Your chosen topic"
```
The outline is built around the actual clips sitting in `clips/approved/` — not a
generic script. Each section maps to a real piece of footage. Check `pipeline/scripted/`.

### Step 5 — Record your voiceover
Record following the outline. Drop the file into `pipeline/recorded/`.

### Step 6 — Assemble the video
```
python assemble_video.py
```
Lays your voiceover over the approved clips in sequence. Finished video lands in `outputs/long-form/`.

### Step 7 — Cut Shorts
```
python generate_shorts.py --video outputs/long-form/your-video.mp4
```
Gemini finds the best moments, the script shows them to you for approval, then cuts
and formats each one as a 9:16 Short with burned-in subtitles. Lands in `outputs/shorts/`.

### Step 8 — Get metadata
```
python generate_metadata.py --video outputs/long-form/your-video.mp4
```
Generates 3 title options, a description, and tags in Dean's voice.
Saved as a `.txt` file next to the video — copy-paste straight into YouTube Studio.

---

## First-Time Setup

1. Copy `config/.env.example` to `config/.env`
2. Fill in your API keys in `config/.env`
3. Fill in `DEAN.md` with your channel details (do this at the Apr 7 kickoff)
4. Fill in `references/tone.md` and `references/phrases.md`
5. Install Python dependencies:
```
pip install yt-dlp feedparser google-generativeai anthropic python-dotenv openai-whisper moviepy
```
6. Make sure FFmpeg is installed: https://ffmpeg.org/download.html

---

## Key Files to Know

| File | Why it matters |
|------|---------------|
| `DEAN.md` | The AI reads this every time — keep it up to date |
| `config/.env` | Your API keys — never share this file |
| `config/feeds.json` | Add or remove news sources here |
| `config/clip_sources.json` | Add or remove highlight channels here |
| `references/tone.md` | Fine-tune how the AI writes in your voice |
| `references/banned_topics.md` | Things the AI will never suggest |

---

## Troubleshooting

- **Script won't run** — make sure you've installed the dependencies and filled in `.env`
- **Clips won't download** — check that `yt-dlp` is up to date: `pip install -U yt-dlp`
- **AI output sounds wrong** — update `DEAN.md` and `references/tone.md` with more examples
- **FFmpeg errors** — confirm FFmpeg is installed and on your PATH: `ffmpeg -version`
