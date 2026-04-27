---
description: Start a new video from ideas to approved script
argument-hint: "[optional topic]"
---

Start a new DeanerHD video.

## Steps

1. If `$ARGUMENTS` is empty, run:

```bash
python scripts/fetch_ideas.py
```

Show the newest file in `pipeline/ideas/` and ask Dean which topic he wants.

2. Choose a clean slug and create/use a project package under
`pipeline/projects/`.

3. Generate the script for the locked topic:

```bash
python scripts/generate_script.py --topic "<topic>" --type auto --project "<slug>"
```

4. Generate metadata from the script:

```bash
python scripts/generate_metadata.py --project "<slug>"
```

5. After Dean approves the script, gather clips from the script cues:

```bash
python scripts/gather_clips.py --project "<slug>" --from-outline --auto --search-provider ytdlp
```

6. Tell Dean to review the project `clips/raw/` and move keepers plus matching
`.json` sidecars into the project `clips/approved/`.

7. Tell Dean to record the voiceover and drop it into the project `voiceover/`,
then say `/assemble <slug>`.

## Guardrails

Reject gameplay, simulations, fan-reaction hosts, podcast panels, generic title
cards, subscribe overlays, visible watermarks when avoidable, and unrelated
talking-head clips. Relevant interviews, scorecards, rankings, and training
footage are allowed when they serve the story. Score/boxscore screenshots should
be overlays on footage, not full-screen slide cards.
