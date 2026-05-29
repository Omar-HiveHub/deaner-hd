# DeanerHD Production Kit

This repo is now a simplified local production assistant for DeanerHD. It no
longer promises upload-ready automated edits. The retained value is ideas,
outlines/scripts, metadata, clip gathering, and clean edit-ready project folders.

Dean-facing instructions live in [START_HERE.md](START_HERE.md).

## Active Folder Guide

| Folder | Purpose |
|---|---|
| `01_Ideas/` | Source reports and topic ideas |
| `02_Projects/` | One folder per video |
| `03_Reference/` | Dean's transcripts, tone notes, phrases, source references |
| `config/` | Setup notes, source lists, and system config |
| `scripts/` | Automation scripts and the simple `dean.py` wrapper |

## Simple Wrapper

Use this wrapper for the handoff workflow:

```bash
python3 scripts/dean.py ideas
python3 scripts/dean.py new "topic name"
python3 scripts/dean.py outline <project>
python3 scripts/dean.py gather <project>
python3 scripts/dean.py gather <project> --section "hit replay"
python3 scripts/dean.py metadata <project>
python3 scripts/dean.py package <project>
```

## Project Shape

New projects live under `02_Projects/YYYY-MM-DD-topic-slug/`:

```text
00_READ_ME.md
01_outline.md
02_script.md
03_metadata.txt
04_clip_cue_sheet.csv

Clips live separately at `clips/<project-name>/raw/`.
```

No thumbnail folder is created. Dean makes thumbnails manually.
Clip gathering searches YouTube, Reddit, and hockey websites like NHL.com,
Sportsnet, TSN, and ESPN in the background.

## What Is Not Promised

- Perfect final video assembly
- Exact transcript-to-clip sync
- Thumbnail creation
- Finished Hockey Psychology-style edits
- Fully automated graphics

Advanced editing is outside the active handoff. Dean gets a clean production
assistant, not an upload-ready video editor.
