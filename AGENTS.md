# AGENTS.md - DeanerHD Operating Brief

This repo is a simplified local production assistant for DeanerHD. Keep Dean's
workflow simple: ideas, outlines/scripts, metadata, organized clip gathering,
cue sheets, and edit-ready project folders.

## Current Promise

- Final editing is manual.
- Thumbnail creation is not part of this system.
- Automated assembly, graphics, and exact transcript-to-clip sync are
  experimental and must not be presented as the default deliverable.
- Clip gathering should search beyond YouTube where useful, including Reddit,
  NHL.com, Sportsnet, TSN, and ESPN when the cue calls for it.

## Folder Rules

- Dean-facing docs stay at root: `START_HERE.md`, `README.md`, `DEAN.md`.
- Active projects live in `02_Projects/`.
- Each project should stay minimal: `00_READ_ME.md`, `01_outline.md`,
  `02_script.md`, `03_metadata.txt`, and `04_clip_cue_sheet.csv`.
  Gathered clips live in the matching top-level `clips/<project-name>/raw/` folder.
- Keep rejected junk, test runs, and internal notes out of Dean-facing folders.
- Preserve `.json` sidecars when reorganizing clip folders. They carry the
  source URL and basic clip metadata.

## Main Commands

Use the wrapper first:

```bash
python3 scripts/dean.py ideas
python3 scripts/dean.py new "topic name"
python3 scripts/dean.py outline <project>
python3 scripts/dean.py gather <project>
python3 scripts/dean.py gather <project> --section "hit replay"
python3 scripts/dean.py metadata <project>
python3 scripts/dean.py package <project>
```

Keep this folder simple enough for Dean to understand from `START_HERE.md`.
