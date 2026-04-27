# Sound Design Assets

The video assembly pipeline (`scripts/assemble_video.py`) uses files in this folder
to layer music and SFX over the voiceover. Files are loaded by **filename**, so
keep these names exactly as listed below — the assembler will silently skip any
file that's missing.

## What's in here right now

| File | What it is | Used when |
|---|---|---|
| `bed_intense.mp3` | 60s loopable synthetic bed | High-conflict stories, fights, playoff tension |
| `bed_reflective.mp3` | 60s loopable synthetic bed | Prospect/player-analysis videos |
| `bed_drive.mp3` | 60s loopable synthetic bed | Faster news/reaction videos |
| `bed_tension.mp3` | 60s loopable synthetic bed | Controversy, stakes, rumours |
| `whoosh.wav` | Legacy transition sweep | Not used by the default minimal edit |

The current files are **synthetic placeholders** generated with FFmpeg — clean,
tasteful, and license-clean (no third-party rights). They get the job done for
the demo cut, but they will not feel like Hockey Psychology production quality.

## Swap in premium assets when you can

For production-grade output, replace each file with a curated royalty-free track.
Same filenames, drop them in this folder, and assembly picks them up automatically.

Recommended sources (all royalty-free for YouTube monetisation):
- **Pixabay Music** — https://pixabay.com/music/  (filter: cinematic / sport)
- **Mixkit** — https://mixkit.co/free-stock-music/  (no attribution required)
- **YouTube Audio Library** — https://studio.youtube.com  (Creator Music tab)

What to look for:
- **bed_intense.mp3**: cinematic sport / drone / trailer beds, 70–110 BPM
- **bed_reflective.mp3**: emotional piano, atmospheric pad, 60–80 BPM
- **whoosh.wav**: cinematic transition, sub-1-second, low-end heavy

After swapping, render a test cut: `python scripts/assemble_video.py --title test`

## SFX Later

The default client edit does not use whooshes or transition SFX. Keep `whoosh.wav`
only as a legacy asset for future experiments.
