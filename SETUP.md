# Setting Up Deaner-HD On A Mac

This is the one-time setup. After this, Dean should work through Codex or Claude
Code and Finder, not Terminal.

## 0. Clone The Repo

In Terminal (one time only):

```bash
git clone https://github.com/Omar-HiveHub/deaner-hd.git
cd deaner-hd
```

Then open the `deaner-hd` folder in Claude Code or Codex.

## 1. Install The Agent App

Use either:

- Codex desktop/app workflow, or
- Claude Code from https://claude.com/code

Open the `Deaner-HD` folder in the app after setup is complete.

## 2. Put The Folder Somewhere Stable

Keep the full `Deaner-HD` folder in one place, such as Desktop or Documents.
The expected top-level folders are:

```text
clips/
config/
outputs/
pipeline/
references/
scripts/
voice/
```

## 3. API Keys

Secrets live in `config/.env`. Omar will provide this file. Do not commit it to Git.

```text
GEMINI_API_KEY=...
YOUTUBE_DATA_API_KEY=...
```

**No Anthropic key needed.** The agent runtime (Claude Code or Codex) provides
model access automatically — just open the folder in the app and start chatting.

## 4. Run The Installer

Double-click `setup.command` in Finder. It checks Python, FFmpeg, packages, and
project folders.

When it finishes, open this folder in Codex or Claude Code and type:

```text
let's start a new video
```

## Daily Workflow

| Step | Dean says/does | Folder |
|---|---|---|
| Start | `let's start a new video` | Agent chat |
| Package | Agent creates a project folder | `pipeline/projects/` |
| Script | Agent writes script and metadata | project `script/`, `metadata/` |
| Gather | Agent gathers clips from script cues | project `clips/raw/` |
| Approve | Drag keepers into approved, with matching `.json` files | project `clips/approved/` |
| Record | Drop the voiceover file | project `voiceover/` |
| Assemble | `assemble the video` | project `exports/` |
| Finish | `write the titles and metadata` | project `metadata/`, `thumbnail/`, `notes/` |

## Troubleshooting

- Missing API key: ask Omar for the current `config/.env` value.
- FFmpeg error: rerun `setup.command`.
- Clip download issue: ask the agent to update `yt-dlp`.
- Video refuses to assemble: approve more clips or gather more. The assembler
  will not loop footage to cover a long voiceover.
- Music feels too synthetic: replace the `config/sfx/bed_*.mp3` placeholders
  with higher-quality royalty-free tracks using the same filenames.

## What Not To Commit

`config/.env`, raw clips, recordings, rendered MP4s, and other large generated
media should stay local unless Omar intentionally enables Git LFS.
