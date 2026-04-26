---
description: Sanity-check the system — API keys, ffmpeg, yt-dlp, disk space
---

Run a fast diagnostic. Don't proceed if any check fails.

## What to do

Run each of these and report results in a checklist format. Don't try to fix anything — just report status. If something fails, tell the user the exact line in SETUP.md to read.

### 1. API keys
```bash
python3 -c "
from pathlib import Path
import os, sys
sys.path.insert(0, 'scripts')
from dotenv import load_dotenv
load_dotenv('config/.env')
checks = [('ANTHROPIC_API_KEY', os.getenv('ANTHROPIC_API_KEY')),
          ('GEMINI_API_KEY', os.getenv('GEMINI_API_KEY')),
          ('YOUTUBE_DATA_API_KEY', os.getenv('YOUTUBE_DATA_API_KEY'))]
for name, v in checks:
    status = 'MISSING' if not v or v == 'your_key_here' else f'set ({len(v)} chars)'
    print(f'  {name}: {status}')
"
```

### 2. FFmpeg
```bash
which ffmpeg || ls /opt/homebrew/bin/ffmpeg
ffmpeg -version 2>&1 | head -1 || /opt/homebrew/bin/ffmpeg -version 2>&1 | head -1
```

### 3. yt-dlp
```bash
python3 -c "import yt_dlp; print('yt-dlp', yt_dlp.version.__version__)"
```

### 4. Whisper
```bash
python3 -c "import whisper; print('whisper installed')"
```

### 5. Anthropic SDK
```bash
python3 -c "import anthropic; print('anthropic', anthropic.__version__)"
```

### 6. Gemini SDK
```bash
python3 -c "import google.generativeai as g; print('google-generativeai installed')"
```

### 7. Disk space (need 5+ GB free)
```bash
df -h ~ | tail -1
```

### 8. SFX assets
```bash
ls -la config/sfx/ 2>/dev/null || echo "config/sfx/ missing — see config/sfx/README.md"
```

## Reporting format

Print a clean checklist:

```
✓ ANTHROPIC_API_KEY set (108 chars)
✗ GEMINI_API_KEY MISSING → see SETUP.md step 3
✓ FFmpeg 8.1
...
```

Mark missing/failing items with ✗ and tell the user what to fix. If everything passes, end with: "All systems go. Run `/new-video` to start."
