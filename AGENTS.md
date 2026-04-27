# AGENTS.md — Deaner-HD Operating Brief

This repo is a local YouTube production system for DeanerHD. Treat it like a
client delivery folder, not a playground.

## How To Help

- Speak plainly and keep Dean out of the terminal whenever possible.
- Prefer running the existing scripts over inventing new workflows.
- Keep generated media local. Do not commit raw clips, voiceovers, rendered MP4s,
  or `config/.env`.
- Preserve sidecar JSON files when moving clips. The assembler uses them for
  source diversity and clip classification.
- Use `pipeline/projects/YYYY-MM-DD-topic-slug/` for new videos so scripts, metadata,
  clips, voiceover, notes, thumbnail brief, and exports stay together.
- Match artifact names to the package: `YYYY-MM-DD-topic-slug-script.md`,
  `YYYY-MM-DD-topic-slug-metadata.txt`,
  `YYYY-MM-DD-topic-slug-thumbnail-brief.txt`, and
  `YYYY-MM-DD-topic-slug-final.mp4`.

## Production Order

1. Fetch weekly ideas and source report.
2. Create or use a project package for the approved topic.
3. Generate the script and metadata into the package.
4. Gather clips from the approved script cues with `--project <slug> --from-outline --auto --search-provider ytdlp`.
5. Dean records the script and drops the voiceover into the package `voiceover/`.
6. Assemble the full video from package-approved clips and the voiceover.
7. Shorts are a later separate workflow, not auto-cut from long-form by default.

## Video Defaults

- Default assembly mode is minimal: source-diverse hard cuts, voiceover, and a
  low music bed.
- Use official screenshot overlays from `timeline/visual-plan.json` when the
  story needs score/boxscore context. Do not use full-screen title cards.
- Use `--no-music` only when the user asks for a strict no-music test.
- Never loop b-roll. If there are not enough clips, gather more.
- Never cut the voiceover mid-sentence. The finished video duration is driven by
  the full voiceover.

## Clip Quality

Accept:

- real NHL/CHL/game footage,
- clearly relevant player/coach/media interviews,
- personal athlete training/workout footage when it directly supports the story,
- official scorecards, standings, stat screenshots, and rankings when held long
  enough to understand, preferably as overlays on active footage.

Reject:

- Xbox, EA Sports, NHL 24/25/26, simulations, franchise mode, gameplay,
- podcast panels and fan-reaction host shots,
- subscribe/like overlays and creator intro screens,
- unrelated full-face commentary or clips where the subject does not match the
  story.

## Current Delivery Demo

Delivery demos live as project packages under `pipeline/projects/`:

- `demo-1-rempe-biggest-target`
- `demo-2-bedard-tkachuk`

Any MP4 outside those packages is a draft unless the project proof note says it
passed full-audio, no-loop, no-abrupt-ending review.
