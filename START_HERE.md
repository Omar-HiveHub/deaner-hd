# Start Here — DeanerHD Production Kit

This folder is a simple YouTube production assistant. It helps with the parts before editing: finding ideas, building an outline, writing optional scripts, gathering clips into organized folders, and creating upload metadata.

It is **not** a finished-video editor. Dean still makes the final edit and thumbnails.

## What This System Does

- Finds hockey topic ideas from news, feeds, Reddit, YouTube signals, and hockey sources.
- Creates Dean-style outlines with hooks, section beats, clip cues, and CTA options.
- Can write a full script when you ask for one.
- Generates title ideas, descriptions, and tags.
- Searches for clips across YouTube, Reddit, and hockey websites like NHL.com, Sportsnet, TSN, and ESPN.
- Saves clips into a clean project folder.
- Builds a cue sheet so clips are easy to review in an editor.

## What This System Does Not Do

- It does not make thumbnails.
- It does not produce a finished upload-ready edit.
- It does not guarantee perfect transcript-to-clip sync.
- It does not replace Dean's final judgment on which clips to keep.
- It does not post to YouTube.

## Folder Map

```text
01_Ideas/       weekly source reports and topic ideas
02_Projects/    one folder per video
03_Reference/   Dean voice notes, past scripts, and transcript references
config/         source lists and setup config
scripts/        system commands used by Codex/the CLI
```

For day-to-day work, Dean mainly opens `02_Projects/` and the project he is working on.

## Normal Workflow

### 1. Get Ideas

Ask Codex:

```text
show me topic ideas for this week
```

Codex will create or update a source report in `01_Ideas/` and suggest topics.

If you already know the topic, skip this step.

### 2. Start A Project

Ask Codex:

```text
start a new video about [topic]
```

Example:

```text
start a new video about Evan Bouchard dirty hit at IIHF Worlds
```

This creates a folder in `02_Projects/` with:

```text
00_READ_ME.md
01_outline.md
02_script.md
03_metadata.txt
04_clip_cue_sheet.csv

Clips are stored separately at `clips/<project-name>/raw/`.
```

### 3. Review Or Adjust The Outline

Open `01_outline.md`. This is the recording structure.

Useful prompts:

```text
make the hook stronger
make section 2 more emotional
add a section about what the league might do next
write this as a full script instead of an outline
```

### 4. Gather Clips

Ask Codex:

```text
gather clips for this project
```

Clips go into `clips/<project-name>/raw/`. The system also saves a matching `.json` file beside each clip so the source URL and timestamp are preserved.

For a specific section, ask:

```text
re-gather clips for the section about the hit replay
```

### 5. Pick Keeper Clips

Open `clips/<project-name>/raw/` and watch the clips. Each clip has two files:

```text
clip-name.mp4
clip-name.json
```

Keep clips that clearly match the story. Skip talking heads, wrong teams, low-quality footage, creator intros, or anything that feels random.

### 6. Generate Upload Copy

Ask Codex:

```text
write the titles and metadata
```

The output goes into `03_metadata.txt`.

### 7. Package For Editing

Ask Codex:

```text
package this project for editing
```

This refreshes `04_clip_cue_sheet.csv`, which Dean can use while editing.

## Example Demo Project

A finished example lives here:

```text
02_Projects/2026-05-29-evan-bouchard-knocked-out-by-dirty-hit-at-worlds/
```

Use it to see what the system produces:

- `01_outline.md` shows the video structure.
- `03_metadata.txt` shows title, description, and tag output.
- `clips/2026-05-29-evan-bouchard-knocked-out-by-dirty-hit-at-worlds/raw/` shows gathered clips.
- `04_clip_cue_sheet.csv` shows the source list for editing.

This demo is already gathered, so you can show it without running another clip search or hitting rate limits.

## Quota-Safe Call Demo

If Omar is showing this live to Dean, use the existing demo project first. Do **not** run a fresh gather command on the call unless needed.

Recommended live flow:

1. Open `START_HERE.md`.
2. Open the Bouchard demo project in `02_Projects/`.
3. Show the outline.
4. Show the metadata file.
5. Show `clips/<project-name>/raw/`.
6. Show `04_clip_cue_sheet.csv`.
7. Explain that future projects follow the same flow.

## Prompt Reference

| Goal | Prompt |
|---|---|
| Find ideas | `show me topic ideas for this week` |
| Start a project | `start a new video about [topic]` |
| Rewrite hook | `make the hook stronger` |
| Full script | `write this as a full script` |
| Gather clips | `gather clips for this project` |
| Gather one section | `re-gather clips for the section about [thing]` |
| Metadata | `write the titles and metadata` |
| Package | `package this project for editing` |
| Status | `show me the current status of this project` |

## If Something Goes Wrong

**No clips came in**

Ask:

```text
check the clip cues in the outline and make them more specific
```

**Clips are too broad**

Ask:

```text
re-gather clips for section 2 and focus only on the actual hit/replay
```

**The outline sounds off**

Ask:

```text
rewrite the outline closer to Dean's voice using the reference transcripts
```

**The metadata is weak**

Ask:

```text
give me 10 stronger title ideas with more curiosity
```

## The Simple Promise

This system gives Dean a clean starting point: topic, outline/script, metadata, gathered clips, and an organized edit folder. It saves time before the edit. The final video is still Dean's creative call.
