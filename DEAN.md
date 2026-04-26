# DEAN.md — Channel Context File
# Deaner-HD YouTube Automation System
#
# Single source of truth for the channel's identity.
# Every AI call in this system loads this file as context.

---

## Channel Overview

- **Channel Name:** DeanerHD
- **Niche:** Vancouver Canucks-focused NHL commentary — game recaps, rebuild/tank analysis, 2026 NHL Draft prospect breakdowns, Olympic hockey coverage
- **Current Subscribers:** ~10,000–20,000 estimated (based on view counts across recent videos)
- **Peak Performing Video:** "This player is becoming the GREATEST Swedish Prospect of all time" (Ivar Stenberg) — 75,000+ views
- **Channel Age:** Active since at least 2021 (has older Stanley Cup Playoff livestreams)
- **Primary Platform:** YouTube (long-form commentary + Shorts)

---

## Voice and Tone

- **Overall Energy:** Passionate die-hard Canucks fan — excited when the team wins, frustrated when management makes bad decisions, fired up on draft talk. Not a screamer — measured but opinionated.
- **Sentence Style:** Conversational and direct. Medium-length sentences that build an argument step by step. Thinks out loud on camera. Not overly scripted — sounds natural and off-the-cuff.
- **Personality Traits:** Confident in his opinions, willing to defend a player when others pile on (e.g., defending McKenna after the bar incident), acknowledges when he's emotionally torn (e.g., rooting for the Canucks to win while knowing they should tank).
- **POV / Perspective:** Die-hard Canucks fan with an analytical eye. Rebuild advocate — believes the draft is the only right way to build a team. Skeptical of short-term "hybrid retool" thinking from management. Trusts the process.
- **How Dean sounds different from other hockey YouTubers:** He covers the Canucks rebuild from a fan's emotional perspective while backing it up with prospect-level analysis most casual fans don't do. He digs into prospects (WHL, NCAA, SHL stats) the way a scout would, but talks about them the way a fan would.

---

## Signature Phrases

- Sign-off: **"Peace out and take care"** — used at the end of every video, always
- Sign-off setup: **"Subscribe if you're new, I'll see you in the next one"** — usually right before peace out
- Engagement CTA: **"Let me know in the comments"** — used mid-video when asking for viewer opinion
- Standard CTA: **"Make sure you like, comment, subscribe"**
- Opener style: **"Alright, so..."** or **"Alright, listen..."** — jumps straight into the point, no preamble
- Reaction phrase: **"This is a joke"** or **"This is starting to get a little bit ridiculous"** — used for ironic/surprising situations
- Approval phrase: **"I love to see that"** or **"Love the [player]"** — when a player has a strong game
- Measured disagreement: **"Look, I mean..."** — before making a nuanced point that pushes back on a take
- Compliment-then-pivot: **"Fair play"** — used after acknowledging something he didn't expect

---

## Topics Covered

- **League-wide NHL stories** — shifting away from Canucks-only recaps toward the best stories across the entire league
- **Player biographies / documentary-style videos** — deep backstory + current season + skill set + draft destination. Model: "Greatest Swedish Prospect" (Stenberg, 75k views)
- **Player spotlights / breaking news** — big moments (fights, incidents, milestones) that create a title mystery ("No one saw what Kachuk did...")
- **2026 NHL Draft prospect breakdowns** — deep dives on McKenna, Stenberg, Verhoff, Lawrence, Malhotra, and others
- **Canucks game recaps** — only when something genuinely notable happened; no longer every game
- **Off-ice player stories with hockey relevance** — e.g. McKenna bar incident/charges when it affects draft stock perception

---

## Topics Never Covered

- Non-hockey sports (no football, basketball, baseball)
- Routine low-stakes Canucks games with nothing notable happening
- Politically charged non-hockey topics
- Gear reviews or equipment content

---

## Competitors

| Channel | Role | Notes |
|---------|------|-------|
| Hockey Psychology | Primary model | Best video quality, structure, scripting — closest benchmark to emulate |
| Nuckhead | Direct competitor | Dean has done collabs; good reference for style |
| Next Man Up | Indirect competitor | Good production quality |
| Rob Talks Hockey | Indirect competitor | Mostly face-to-camera; not the model but worth watching |

- See config/competitors.json for full structured data

---

## Clip Sources

- NHL official highlights (YouTube)
- Sportsnet highlights
- TSN highlights
- See config/clip_sources.json for full structured data

---

## Upload Schedule and Goals

- **Target upload cadence:** Every 3 days (confirmed from analytics — views exhaust at ~5 days, so 3-day window maximises growth before decay)
- **Long-form length:** 4–6 minutes. Shorter is fine if the story fits. Not shorter than 3 min.
- **Shorts per video:** 3 Shorts cut from each long-form video to start; scale volume later based on which perform best
- **Sub goal (3-month):** 25,000 subscribers
- **View goal (3-month):** 500,000 total views

---

## Recording Setup

- **Primary content:** Talking-head commentary style with hockey clips as b-roll
- **File format Dean records in:** MP4 / M4A
- **Storage location for recordings:** pipeline/recorded/

---

## Workflow Preference

- **Auto-upload vs manual review:** Manual review before upload. Auto-draft to YouTube Studio is a future feature once local is stable.
- **Which steps Dean wants to approve manually:** Clip selection (move raw → approved), outline review, metadata review before posting
- **How much editing Dean does himself vs automated:** Automated clip assembly, manual final check
- **Preferred review format:** File drop — check pipeline/ and outputs/ folders
- **Outline format:** TBD — Dean sending sample documents + voicemail to confirm preferred style (full script vs hook + bullets + CTA)
- **Execution environment:** Local on Dean's Mac. Omar provides setup scripts so Dean never needs to touch terminal. Hosted drag-and-drop UI planned after local setup is stable.

---

## Workflow

The confirmed 8-step production flow for every video:

1. **Fetch ideas** — run `fetch_ideas.py` to pull latest NHL news and trending content. Pick the topic from `pipeline/ideas/`.
2. **Gather clips** — run `gather_clips.py --topic "..."`. Clips download to `clips/raw/`.
3. **Approve clips** — move keepers to `clips/approved/`. Everything else stays in raw.
4. **Generate script** — run `generate_script.py --topic "..." --type incident|biography`. Output lands in `pipeline/scripted/`. Produces a complete ready-to-record prose script in Dean's voice — not bullet points.
5. **Record voiceover** — record following the outline. Drop file into `pipeline/recorded/`.
6. **Assemble video** — run `assemble_video.py`. Exports to `outputs/long-form/`.
7. **Generate Shorts** — run `generate_shorts.py`. Gemini detects moments, clips reframed to 9:16, subtitled. Output: `outputs/shorts/`.
8. **Generate metadata** — run `generate_metadata.py`. 3 title options, description, tags. Output: `outputs/long-form/[video]-metadata.txt`.

---

## Current Pain Points

- No automated way to find topic ideas — manually scrolling Twitter/Reddit currently
- Clip sourcing is manual — have to find highlights on YouTube, download separately
- Metadata generation takes too long — writing titles and descriptions from scratch every video
- No Shorts workflow — ideas die because cutting and subtitling manually takes too long
- Low CTR from poor thumbnails — high-quality, focused thumbnails with compelling text are a known gap
- Copyright claims from consecutive clips — clips stacked back-to-back trigger claims even at 5s each. Fix: alternate clips with stat boards, screenshots, or other visual breaks

## Copyright Rules (CRITICAL)

- **5-second rule:** No single clip longer than 5 seconds
- **No consecutive clips:** Never stack clips directly together — always break them up with a stat board, player screenshot, or graphic
- **Varied visuals:** Mix in pop-ups (stats, player photos, overlaid text) throughout to both confuse the copyright detector and improve viewer experience

---

## Video Quality Signals

What makes a DeanerHD video perform well (from kickoff call analysis):
- **Title creates a question or mystery** — "No one saw what Kachuk did..." / "What happens when you're the NHL's biggest target"
- **Thumbnail is high-quality and focused** — two players clearly visible, clear text, no zoomed-out blurry shots
- **Story-driven structure** — backstory → current season → skill analysis → draft destination → viewer question
- **Engagement CTA at end** — pose a specific question to the audience so comments are directed
- **Sound effects and mood music** — clicks, thuds, transitions, mood shifts (sad → upbeat). Dean wants this added and has competitors as examples.
- **Video length 4–6 minutes** — long enough to build the story, short enough to hold attention

## Audio / Sound Design (Needed)

- Dean wants contextual sound effects added at key moments (e.g. a click or thud on a hit, mood music under a sad player story segment)
- Inspired by competitor Hockey Psychology's use of audio layers
- Dean will send specific timestamped examples from competitors showing exactly what he means
- This should be part of the `assemble_video.py` step — background music track + SFX cue points

## System Notes

- **2026-04-13** — Kickoff call held Apr 6. Content strategy updated: league-wide stories > Canucks-only recaps. Competitors confirmed. Cadence locked at every 3 days. Copyright rules documented. YouTube Manager access granted. Demo was planned Apr 11-12.
- **2026-04-05** — DEAN.md filled in from analysis of 10 transcribed videos (Dec 2025–Mar 2026). Channel is deep in Canucks rebuild coverage and 2026 NHL Draft prospect mini-series (McKenna, Stenberg, Verhoff, Lawrence, Malhotra). Peak views on Stenberg video (75k). Sign-off is always "peace out and take care."
- **2026-04-04** — System scaffold created. All sections marked for kickoff Apr 7.
