---
description: Build the long-form video from approved clips and recorded voiceover
argument-hint: "[optional --title slug] [--no-music] [--retention]"
---

Build the long-form video.

## Steps

1. Treat `$ARGUMENTS` as the project slug when present.
2. Confirm the project `clips/approved/` contains `.mp4` files with matching `.json` sidecars.
3. Confirm the project `voiceover/` contains the intended voiceover.
4. Pick a title slug from `$ARGUMENTS` or the project folder name.
5. Run the default minimal edit:

```bash
python scripts/assemble_video.py --project "<slug>" --title "<slug>"
```

If the user asks for a strict test with no music/cards:

```bash
python scripts/assemble_video.py --project "<slug>" --title "<slug>" --no-music
```

## What To Watch For

- The assembler must not loop footage.
- The voiceover must finish naturally; no abrupt mid-sentence ending.
- If it says there are not enough clips, stop and gather/approve more clips.
- The output lands in the project `exports/` folder.
- Official screenshots in `timeline/visual-plan.json` render as overlays on the
  b-roll, not as full-screen cards.

End by telling the user the exact output path and asking them to watch it once
cold for irrelevant faces, gameplay, subscribe overlays, and creator title cards.
