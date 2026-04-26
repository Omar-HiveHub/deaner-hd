# Setting up Deaner-HD on your Mac

This is a one-time install. Once you finish these 5 steps, you'll never touch
the terminal again — you'll just open the folder in Claude Code and chat.

**Estimated time:** 10–15 minutes (most of that is one-time downloads).

---

## Step 1 — Install Claude Code

Claude Code is the desktop app you'll use as your control panel.

1. Go to https://claude.com/code
2. Click **Download for Mac**
3. Run the installer. Accept the prompts.

Once it's installed, **don't open it yet** — finish the other steps first.

---

## Step 2 — Make sure the Deaner-HD folder is in the right place

Drop the entire `Deaner-HD` folder onto your **Desktop** (or anywhere you like —
just remember where it is).

The folder structure should look like this:

```
Deaner-HD/
├── CLAUDE.md
├── DEAN.md
├── SETUP.md          ← (you're reading this)
├── README.md
├── requirements.txt
├── setup.command     ← (you'll double-click this in Step 4)
├── config/
│   └── .env          ← (you'll edit this in Step 3)
├── clips/
├── pipeline/
├── outputs/
├── references/
├── scripts/
├── voice/
└── .claude/
    └── commands/
```

---

## Step 3 — Add your API keys

The system needs three keys to do its work. Replacements take 30 seconds.

1. Open `Deaner-HD/config/.env` in any text editor (TextEdit is fine — File →
   Open → navigate to it).

2. You'll see three lines like this:
   ```
   ANTHROPIC_API_KEY=your_key_here
   GEMINI_API_KEY=your_key_here
   YOUTUBE_DATA_API_KEY=AIzaSy...
   ```

3. Replace each `your_key_here` with the real key.

   **Where to get each key:**

   | Key | Where to get it | Why we need it |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | https://console.anthropic.com → Settings → API Keys → Create Key | Writes scripts + metadata in your voice |
   | `GEMINI_API_KEY` | https://aistudio.google.com/apikey → Create API key | Picks the best moments to cut as Shorts |
   | `YOUTUBE_DATA_API_KEY` | https://console.cloud.google.com → APIs & Services → Credentials → Create credentials → API key | Pulls fresh news & finds clip sources |

   `YOUTUBE_DATA_API_KEY` may already be filled in — if so, leave it alone.

4. **Save the file** (⌘S in TextEdit).

> **Don't share this file or commit it to git.** Your keys are tied to your
> billing — if someone else gets them, they spend your money.

---

## Step 4 — Run the installer

Double-click `Deaner-HD/setup.command` in Finder.

A black Terminal window will open. The installer will:

- Verify Python 3.11+ is installed (warns and points you to a download if not).
- Install [Homebrew](https://brew.sh) if missing (it's the standard Mac package
  manager — installer prompts for your password once).
- Install [FFmpeg](https://ffmpeg.org) — required to assemble video.
- Create a Python virtual environment in `.venv/`.
- Install all Python packages from `requirements.txt`.
- Run a final health check confirming everything is wired up.

You'll see lines scrolling by for ~5–10 minutes. When it's done, you'll see:

```
✓ Setup complete. Open the Deaner-HD folder in Claude Code and type:
     let's start a new video
```

If anything fails, the installer prints which step broke and what to do.
You can re-run it as many times as you want — it's idempotent.

---

## Step 5 — Open the folder in Claude Code

1. Launch **Claude Code** (you installed it in Step 1).
2. File → Open Folder → choose `Deaner-HD`.
3. In the chat box, type:
   ```
   let's start a new video
   ```

Claude Code reads `CLAUDE.md` and walks you through the pipeline. Just talk to
it like you'd talk to a producer.

---

## Day-to-day workflow

Once setup is done, every video looks like this:

| Step | What you say in Claude Code | What you do off-screen |
|---|---|---|
| 1 | "let's start a new video" or `/new-video` | Pick a topic from the list |
| 2 | (Claude runs gather_clips automatically) | Drag keepers from `clips/raw/` to `clips/approved/` |
| 3 | "ready for the script" | Read the script Claude generates |
| 4 | (off-screen) | Record voiceover, drop file in `pipeline/recorded/` |
| 5 | `/assemble` | Watch the rendered long-form |
| 6 | `/finalize` | Approve Shorts, copy metadata to YouTube Studio |

---

## Slash commands you'll use

- `/new-video [topic]` — start a fresh video
- `/assemble` — build the long-form from approved clips + voiceover
- `/finalize` — cut Shorts and generate metadata
- `/health` — quick sanity check on API keys, FFmpeg, etc.

---

## Troubleshooting

**"ANTHROPIC_API_KEY not set"** → Open `config/.env` and replace `your_key_here`
with your real key (Step 3).

**"FFmpeg not found"** → Re-run `setup.command`. If that fails, install
manually: open Terminal, paste `brew install ffmpeg`, hit Enter.

**Clip download fails** → YouTube changes the rules sometimes. Open Terminal in
`Deaner-HD/`, run `pip install -U yt-dlp`, try again.

**Script doesn't sound like me** → Open `references/tone.md` and add an example
of how a sentence *should* have sounded. The next script gets better.

**FFmpeg "drawtext: filter not found"** → That's the visual break renderer
falling back to Pillow — already handled, no action needed.

**Want better music / SFX** → Drop royalty-free files into `config/sfx/` with
the same filenames listed in `config/sfx/README.md`. The placeholders that
ship with the system are clean but synthetic.

---

## What's safe to delete or move

- **Don't move:** `CLAUDE.md`, `DEAN.md`, anything in `scripts/`, `config/`,
  `references/`, `voice/`.
- **Free to clean out periodically:** `clips/raw/` (after approving clips),
  `pipeline/ideas/` (after picking a topic), old files in `outputs/long-form/`
  once they're published to YouTube.
- **Keep around:** `voice/transcripts/` — these are your voice training data.
  More transcripts = better script generation over time.

---

## When something goes really wrong

Type `/health` in Claude Code. It runs through every dependency and tells you
exactly what's missing. Reply with the output to your producer (Omar) if you
can't figure it out.
