# Clips

`clips/raw/` is the legacy flat review folder. New packaged videos use
`pipeline/projects/<video>/clips/raw/`.

Dean reviews those files in Finder and moves keepers into `clips/approved/`.
Move the matching `.json` sidecar with each video file. The JSON tells the
assembler which source video a clip came from.

Skip gameplay, podcast panels, fan reactions, subscribe/like overlays, creator
intro screens, and random talking heads.
