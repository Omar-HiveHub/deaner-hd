# Deaner-HD

This folder is Dean's local video production workspace. Dean can open it in
Codex or Claude Code, describe the video he wants, approve clips in Finder, drop
in a voiceover, and ask the agent to assemble the finished edit.

For the non-technical workflow, start with [START_HERE.md](START_HERE.md).

## What The System Does

1. Finds topic ideas from hockey feeds and competitor channels.
2. Creates one project package per video under `pipeline/projects/`.
3. Generates scripts and metadata from approved ideas.
4. Gathers real hockey clips from the approved script cues.
5. Lets Dean approve raw clips by dragging files in Finder.
6. Assembles long-form videos with source-diverse hard cuts, voiceover, and an
   optional low music bed.
7. Leaves Shorts as a separate later workflow.

## Folder Guide

| Folder | What it is for |
|---|---|
| `clips/raw/` | Auto-downloaded clips waiting for review |
| `clips/approved/` | Clips Dean approved for the edit |
| `pipeline/ideas/` | Topic ideas |
| `pipeline/scripted/` | Script inbox for fresh Claude/Codex scripts |
| `pipeline/recorded/` | Voiceovers Dean records |
| `outputs/long-form/` | Finished long-form videos and delivery notes |
| `outputs/shorts/` | Finished Shorts |
| `pipeline/projects/` | One nested package per client video |
| `voice/transcripts/` | Dean's prior-video transcripts, organized by year |
| `config/` | API keys, clip sources, SFX/music placeholders |
| `scripts/` | Automation code |

## Agent Workflow

Dean can use normal language:

```text
let's start a new video about Matt Rempe
```

The agent should fetch ideas, generate the script and metadata, gather clips
from the script, tell Dean to approve the keepers, wait for the voiceover, and
assemble the video.

Key commands still exist for power users:

```bash
python scripts/fetch_ideas.py --sources-only
python scripts/generate_script.py --topic "Matt Rempe Rangers Leafs fight" --type incident --project rempe-demo
python scripts/generate_metadata.py --project rempe-demo
python scripts/gather_clips.py --project rempe-demo --from-outline --auto --search-provider ytdlp
python scripts/assemble_video.py --project rempe-demo --title rempe-demo
python scripts/generate_thumbnail.py --project rempe-demo
```

Project packages use the same date + slug in every final artifact:
`pipeline/projects/YYYY-MM-DD-topic-slug/script/YYYY-MM-DD-topic-slug-script.md`,
`metadata/YYYY-MM-DD-topic-slug-metadata.txt`,
`thumbnail/YYYY-MM-DD-topic-slug-thumbnail-brief.txt`, and
`exports/YYYY-MM-DD-topic-slug-final.mp4`.

## Clip Safety Rules

- New downloads are capped at 2 clips per source video.
- Clips are 3.0s to 4.9s.
- Gameplay, Xbox/EA Sports, simulations, podcast panels, fan-reaction hosts,
  subscribe/like overlays, and creator intro screens are rejected.
- Relevant game clips are preferred. Relevant player/coach/media interviews and
  clean graphics are allowed when they serve the story.
- Assembly never loops b-roll. If clips are not long enough for the voiceover,
  it exits with a clear error.
- Final videos must finish the full voiceover naturally. Never cut mid-sentence.

## Setup

Run [SETUP.md](SETUP.md) once, then use [START_HERE.md](START_HERE.md) for day
to day operation.

Keep `config/.env`, raw clips, recordings, and rendered media out of Git unless
you intentionally move to Git LFS.
