# Second Brain

Personal wiki powered by Claude Code. Capture raw markdown, let Claude distill and link it, then query it to produce briefs and documents.

## Quick start

```bash
# 1. Create venv and install deps
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your Gemini API key
echo "GEMINI_API_KEY=your-key-here" > .env

# 3. Drop a file into wiki/raw/
echo "# Some thought" > wiki/raw/2026-04-09-test.md

# 4. In Claude Code, run:
/ingest          # process new raw files into notes/
/brief <topic>   # generate a brief from notes/
/garden          # weekly cleanup
```

## Layout

```
wiki/
  raw/       # append-only captures
  notes/     # distilled, interlinked wiki
  outputs/   # generated briefs/docs/decks
  lancedb/   # LanceDB vector store (auto-generated)
  index.db   # SQLite metadata (auto-generated)
scripts/
  ingest.py  # helpers for stamping frontmatter + ledger
  reindex.py # rebuilds LanceDB + SQLite from notes/
  search.py  # semantic search, tag filter, backlinks
.claude/
  commands/  # /ingest, /brief, /garden
  skills/    # jina-capture
  settings.json
CLAUDE.md    # conventions Claude follows every session
```

See `CLAUDE.md` for conventions.
