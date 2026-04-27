# Start Here

Dean, this is the simple version.

## Make A New Video

1. Open this folder in Codex or Claude Code.
2. Type:
   ```text
   let's start a new video
   ```
3. Pick a topic when the agent gives you options.
4. The agent creates one project folder for the video in `pipeline/projects/`.
5. The agent writes the script and metadata first.
6. Approve the script.
7. The agent gathers clips from the script's visual cues into that project's `clips/raw/`.
8. Open the project's `clips/raw/` in Finder and drag the keepers into its `clips/approved/`.
   Move the matching `.json` file with each clip.
9. Record your voiceover and drop it into the project's `voiceover/` folder.
10. Type:
   ```text
   assemble the video
   ```
11. Watch the finished MP4 in the project's `exports/` folder.

## What Good Clips Look Like

Keep real game footage, relevant interviews, and useful graphics.

Skip gameplay, podcast panels, fan reactions, subscribe/like overlays, creator
intro screens, generic title cards, random talking heads, visible watermarks,
and anything that does not clearly match the story.

## Need Titles Or Metadata?

After the video looks good, type:

```text
write the titles and metadata
```

The agent will create a text file next to the finished video.
