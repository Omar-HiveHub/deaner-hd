---
description: Build the long-form video from approved clips + recorded voiceover
argument-hint: "[optional --title slug] [biography|incident|general]"
---

User has approved clips and recorded a voiceover. Build the long-form video.

## What to do

1. **Verify prerequisites:**
   - Confirm `clips/approved/` has at least one .mp4 with a matching .json sidecar.
   - Confirm `pipeline/recorded/` has a recent audio/video file. If the most recent file is older than the most recent clip, ask: "I see voiceover [filename] from [time] — is that the one you want, or did you record something newer?"
   - If either folder is empty, tell the user what's missing and stop.

2. **Pick the topic-type from arguments or context.**
   - If user passed `biography`, `incident`, or `general` in `$ARGUMENTS`, use that.
   - Otherwise, look at `pipeline/scripted/` for the most recent script and infer from the filename or its content (player deep-dive → biography; reaction/incident → incident).
   - If still unsure, ask the user.

3. **Build a slug for `--title`:**
   - If user passed `--title <slug>` in `$ARGUMENTS`, use it.
   - Otherwise, derive from the most recent `pipeline/scripted/` filename (lowercased, dashed).

4. **Run:**
   ```bash
   python scripts/assemble_video.py --topic-type <type> --title <slug>
   ```

5. **Watch the output for these confirmations:**
   - "B-roll built: Xs, N break cards inserted" — if N is 0, warn the user that copyright protection didn't trigger any breaks (this means metadata is missing — re-gather clips).
   - "Exported to outputs/long-form/..." — show the user the output path.

6. **End with:** "Long-form is ready. Watch it once cold to check the cut. When you're happy, say `/finalize` to cut Shorts and generate metadata."

## Defaults & guardrails

- Don't run `--clips-only` unless the user explicitly asks for a "preview" or "b-roll only".
- If `assemble_video.py` reports "no music bed found" or "no whoosh SFX found", that's only a warning — the video still ships. Tell the user once but don't keep flagging it.
- If FFmpeg errors out, show the last 20 lines of stderr and stop. Don't silently retry.
