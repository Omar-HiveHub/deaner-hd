# Outputs

Finished videos and delivery notes land here.

- `long-form/`: full YouTube uploads, metadata notes, thumbnail briefs.
- `shorts/`: reserved for the later Shorts system. For now, Shorts are not
  generated automatically from long-form videos because the tone needs a
  separate 20-30 second script.

New client-ready videos should live in `pipeline/projects/<video>/exports/`
with their script, metadata, thumbnail brief, and proof notes beside them.
`outputs/long-form/` remains a compatibility folder for older flat renders.

Rendered MP4s are local media files and should not be committed to Git unless
Omar intentionally enables Git LFS.
