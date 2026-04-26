---
description: Start a new video — fetch ideas (or accept a topic), gather clips, write the script
argument-hint: "[optional topic]"
---

User wants to start a new video. Arguments: `$ARGUMENTS`

## What to do

1. **If `$ARGUMENTS` is empty**, run `python scripts/fetch_ideas.py` and show the user the resulting markdown file in `pipeline/ideas/`. Ask which topic they want to make. Wait for their answer before continuing.

2. **Once the topic is locked**, ask: "Is this a biography (player deep-dive, draft prospect breakdown — Stenberg/McKenna template) or an incident (Leafs drama, fight, news reaction)?" — this picks the model. Default to `biography` if the topic mentions a single player as a deep-dive subject; default to `incident` for game-day reactions, fights, or "what just happened" stories.

3. **Gather clips:**
   ```bash
   python scripts/gather_clips.py --topic "<the topic>"
   ```
   Tell the user clips landed in `clips/raw/` and to drag the keepers into `clips/approved/` (with their .json sidecars) before saying "ready for the script."

4. **Once user confirms clips are approved**, generate the script:
   ```bash
   python scripts/generate_script.py --topic "<the topic>" --type <biography|incident|general>
   ```
   Show the resulting file from `pipeline/scripted/`. Ask the user to read it through and tell you if anything needs editing — they can either ask you to regenerate or open the file directly.

5. **End with:** "When you've recorded the voiceover and dropped it into `pipeline/recorded/`, say `/assemble` to build the video."

## Defaults & guardrails

- Always run scripts from the project root.
- Never run `gather_clips.py` without an explicit `--topic`.
- If the user wants to override `--type`, respect it. If they're unsure, recommend `biography` for any player-name-led topic and `incident` for everything else.
- If the API key check fails (`ANTHROPIC_API_KEY` not set), point them at `config/.env` and SETUP.md step 3 — don't try to "fix" it yourself.
