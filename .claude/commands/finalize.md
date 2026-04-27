---
description: Generate final metadata, thumbnail brief, and proof note for a project
argument-hint: "[project slug]"
---

Wrap up a finished long-form video package. Shorts are parked for the later
separate short-form system and should not run automatically.

## Steps

1. Treat `$ARGUMENTS` as the project slug.
2. Generate or refresh metadata:

```bash
python scripts/generate_metadata.py --project "<slug>"
```

3. Generate or refresh the thumbnail brief:

```bash
python scripts/generate_thumbnail.py --project "<slug>"
```

4. Confirm the project proof note exists after assembly.

5. Report:

- long-form path,
- metadata text path,
- thumbnail brief path,
- proof note path.

If the user explicitly asks for Shorts, remind them that Shorts are the later
separate workflow and ask before running anything.
