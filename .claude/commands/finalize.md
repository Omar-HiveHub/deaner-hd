---
description: Cut Shorts and generate YouTube metadata for the latest long-form video
argument-hint: "[optional path to video]"
---

User has a finished long-form video and wants to wrap up. Run Shorts + metadata.

## What to do

1. **Find the target video.**
   - If `$ARGUMENTS` is a file path, use it.
   - Otherwise, pick the most recent .mp4 in `outputs/long-form/`.
   - Confirm with the user: "Wrapping up `<filename>` — Shorts + metadata. Go?"

2. **Cut Shorts:**
   ```bash
   python scripts/generate_shorts.py --video outputs/long-form/<filename>.mp4 --title <slug>
   ```
   The script will pause for review and show proposed clips. Pass through whatever the user types to the script's interactive prompt (`y` to accept all, or comma-separated indices like `1,3,4`).

   When done, list the Shorts that landed in `outputs/shorts/`.

3. **Generate metadata:**
   ```bash
   python scripts/generate_metadata.py --video outputs/long-form/<filename>.mp4
   ```
   Uses Claude Haiku 4.5. Output is `outputs/long-form/<filename>-metadata.txt` — show the user the contents.

4. **End with:**
   - "Long-form ready: `outputs/long-form/<filename>.mp4`"
   - "Shorts ready: `outputs/shorts/`"
   - "Metadata ready: `outputs/long-form/<filename>-metadata.txt` — open it and copy-paste into YouTube Studio."

## Guardrails

- Don't run if the long-form video doesn't exist yet — tell the user to run `/assemble` first.
- If `generate_shorts.py` fails on Gemini moment detection, that's almost always the GEMINI_API_KEY missing — point at SETUP.md step 3.
- If the user wants only metadata (no Shorts), respect that — skip step 2 and run only step 3.
