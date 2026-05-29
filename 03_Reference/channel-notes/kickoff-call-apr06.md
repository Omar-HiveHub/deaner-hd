# Kickoff Call Notes — April 6, 2026
**Recording:** https://fathom.video/share/y12efqSRespy45URknAZFikD4LLsi43v
**Duration:** ~48 minutes
**Attendees:** Omar Shakeel, Dean Tsamis

---

## YouTube Access

- Dean granted Omar **Manager** access to his YouTube Studio channel
- This is required to generate a YouTube Data API key for the AI agent
- API key will allow the agent to search videos, fetch transcripts, and eventually auto-draft uploads

---

## Dean's Existing Workflow (Pre-Automation)

1. Idea (mental or rough notes)
2. Rough outline — bullet points / section headers, not full script
3. Record voiceover (improvised from outline)
4. Gather clips manually to match audio
5. Edit video (sync clips to voiceover)
6. Add metadata (title, description, tags)
7. Make thumbnail
8. Upload

**Key insight:** Dean records first, then gathers clips to match. The new workflow moves clip gathering to BEFORE recording so clips are visible during the outline phase.

---

## New AI-Powered Workflow (Confirmed)

1. **Topic generation** — Dean asks agent for ideas; agent pulls from news/Reddit/RSS
2. **Outline generation** — Dean picks topics; agent writes outline in Dean's voice
3. **Clip gathering** — agent sources clips using 5-second rule + varied visuals (stat boards, screenshots) to break up consecutive clips
4. **Dean records voiceover** using the AI outline
5. **Dean drops recording into agent** — agent assembles video (audio + clips synced)
6. **Agent generates metadata** — title (3 options), description, tags
7. **Future:** agent auto-uploads/drafts to YouTube via API

---

## Content Strategy (Updated)

### Shift
- **Away from:** Canucks-only game recaps after every game (stale when team loses or nothing happens)
- **Toward:** League-wide stories — best stories from the full NHL, not one team

### Video Types
1. **Documentary / biography** — player backstory → current season → skill analysis → draft destination. Example: Stenberg video (75k views)
2. **Event / moment** — big play, fight, incident. Hook: title leaves a question. Example: "No one saw what Kachuk did to Condo Bedard"
3. **News / analysis** — breaking NHL news with Dean's take

### Title Strategy
- Always create a question or mystery the viewer HAS to resolve by watching
- Examples: "No one saw what Kachuk did right here" / "What happens when you're the NHL's biggest target"
- Thumbnails must be high-quality, focused, with two clearly recognizable players

---

## Competitors (Confirmed)

| Channel | Priority | Notes |
|---------|----------|-------|
| Hockey Psychology | #1 model | Best structure, scripting, audio design. Emulate this. |
| Nuckhead | #2 | Dean has collaborated; direct competitor |
| Next Man Up | #3 | Solid production |
| Rob Talks Hockey | #4 | More face-to-camera; indirect |

---

## Posting Cadence

- **Target:** Every 3 days
- **Why:** Dean's analytics show views exhaust in ~5 days; 3-day window maximizes momentum before decay
- **Shorts:** 3 Shorts per long-form video initially; private underperformers and scale what works

---

## Audio / Sound Design

Dean wants contextual audio added to videos:
- **Sound effects** — click on a big hit, thud at a physical moment
- **Mood music** — sad/reflective under a difficult player story; upbeat for a comeback moment
- Inspired by Hockey Psychology's audio production
- **Dean will send timestamped examples from competitor videos**
- This needs to be built into `assemble_video.py`

---

## Copyright Rules (Confirmed)

- **5-second max** per clip
- **Never consecutive clips** — always break them up with stat boards, player photos, text overlays
- Dean gets claimed ~1 in every 10–15 videos when he forgets this
- Fix: second or third upload attempt usually clears it, but automation should prevent it

---

## Technical Setup

- **Dean's Mac:** Low storage (~10%), needs to free up ~5 GB
- **Execution:** Local on Dean's Mac to start
- **Terminal:** Dean has never used terminal — Omar will create setup scripts so he never needs to
- **Phase 2:** Hosted drag-and-drop dashboard UI (after local setup is stable and proven)
- **YouTube API:** Will be connected to allow automated draft uploads as a future feature

---

## Outline Format

- Dean's current outlines are rough — mostly bullet points / section headers, not full scripts
- He improvises the voiceover from the points
- Omar asked Dean to send a folder of past written outlines + a voicemail explaining preferred format
- Three format options presented:
  1. **Full word-by-word script**
  2. **3 hook options + section outline + 3 CTA options**
  3. **1 hook + bullet points + 1 CTA** (simplest)

---

## Action Items

### Omar
- [x] Get Manager access to Dean's YouTube Studio
- [ ] Generate YouTube Data API key
- [ ] Build and demo the agent (demo call was targeted Apr 11–12)
- [ ] Install system on Dean's Mac + connect YouTube API
- [ ] Build setup scripts so Dean never touches terminal
- [ ] Add sound effects / mood music layer to `assemble_video.py`
- [ ] Build hosted UI dashboard (Phase 2, after local is stable)

### Dean
- [ ] Share Google Drive folder of past written outlines/scripts
- [ ] Send voicemail explaining preferred outline format
- [ ] Free up ~5 GB disk space on Mac
- [ ] Send timestamped audio examples from competitor videos (for sound design reference)

---

## Timeline (from call)

| Date | Milestone |
|------|-----------|
| Apr 6 | Kickoff call ✓ |
| Apr 11–12 | Demo call / walkthrough (targeted) |
| Apr 17 | System in full operation (Dean's target) |
| Post-stable | Phase 2: hosted UI dashboard |
